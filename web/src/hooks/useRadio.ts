/**
 * useRadio — main hook connecting WebSocket state + audio playback.
 * isPlaying is always driven by the actual audio element, never server state.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { RadioSocket } from "../lib/ws";
import { AudioManager } from "../lib/audio";

export type NowPlaying = {
  id: string;
  tags: string;
  bpm: number | null;
  key_scale: string | null;
  time_signature: number | null;
  instrumental: boolean;
  rationale: string;
  audio_url: string;
  duration: number | null;
  radio: string;
};

export type RadioState = {
  connected: boolean;
  radioName: string;
  isFirstRun: boolean;
  nowPlaying: NowPlaying | null;
  isPlaying: boolean;   // actual audio element state — always accurate
  elapsed: number;      // local audio time
  duration: number;     // local audio duration
  volume: number;
  generating: boolean;
  generationElapsed: number;
  generationParams: Record<string, unknown> | null;
  error: string | null;
};

export function useRadio() {
  const [state, setState] = useState<RadioState>({
    connected: false,
    radioName: "default",
    isFirstRun: true,
    nowPlaying: null,
    isPlaying: false,
    elapsed: 0,
    duration: 0,
    volume: 80,
    generating: false,
    generationElapsed: 0,
    generationParams: null,
    error: null,
  });

  const socketRef = useRef<RadioSocket | null>(null);
  const audioRef = useRef<AudioManager | null>(null);
  const started = useRef(false);
  // Refs to avoid stale closures in start()
  const nowPlayingRef = useRef<NowPlaying | null>(null);
  const serverElapsedRef = useRef(0);

  const showToast = useCallback((msg: string) => {
    toast(msg);
  }, []);

  useEffect(() => {
    const audio = new AudioManager({
      onTimeUpdate: (elapsed, duration) => setState((s) => ({ ...s, elapsed, duration })),
      onPlayStateChange: (isPlaying) => setState((s) => ({ ...s, isPlaying })),
      onEnded: () => socketRef.current?.send("track_ended"),
      onError: () => {
        showToast("Track unavailable — skipping...");
        setTimeout(() => socketRef.current?.send("skip"), 3000);
      },
    });
    audioRef.current = audio;
    return () => audio.destroy();
  }, [showToast]);

  useEffect(() => {
    const setupMedia = (np: NowPlaying) => {
      audioRef.current?.setupMediaSession({
        title: np.tags || "Personal Radio",
        artist: `${np.bpm || "?"} BPM - ${np.key_scale || "?"}`,
        onPlay: () => socketRef.current?.send("resume"),
        onPause: () => socketRef.current?.send("pause"),
        onNextTrack: () => socketRef.current?.send("skip"),
      });
    };

    const socket = new RadioSocket({
      onMessage: (msg) => {
        switch (msg.type) {
          case "sync":
            nowPlayingRef.current = msg.data.now_playing;
            serverElapsedRef.current = msg.data.playback?.elapsed || 0;
            setState((s) => ({
              ...s,
              radioName: msg.data.radio_name,
              isFirstRun: msg.data.is_first_run,
              nowPlaying: msg.data.now_playing,
              volume: msg.data.playback?.volume ?? s.volume,
              generating: msg.data.generating,
            }));
            if (msg.data.now_playing?.audio_url && started.current) {
              audioRef.current?.playTrack(
                msg.data.now_playing.audio_url,
                msg.data.playback?.elapsed || 0
              );
            }
            break;

          case "now_playing":
            nowPlayingRef.current = msg.data;
            setState((s) => ({ ...s, nowPlaying: msg.data }));
            if (started.current && msg.data.audio_url) {
              const audio = audioRef.current;
              if (audio?.hasSource && !audio.paused) {
                audio.crossfadeTo(msg.data.audio_url);
              } else {
                audio?.playTrack(msg.data.audio_url);
              }
              setupMedia(msg.data);
            }
            break;

          case "playback_state":
            // Only sync volume — play/pause state is owned by audio element
            setState((s) => ({ ...s, volume: msg.data.volume ?? s.volume }));
            break;

          case "tick":
            serverElapsedRef.current = msg.data.elapsed;
            break;

          case "generation_start":
            setState((s) => ({
              ...s,
              generating: true,
              generationElapsed: 0,
              generationParams: msg.data.params,
            }));
            break;

          case "generation_progress":
            setState((s) => ({ ...s, generationElapsed: msg.data.elapsed }));
            break;

          case "generation_done":
            setState((s) => ({ ...s, generating: false, generationElapsed: 0, generationParams: null }));
            break;

          case "regenerating":
            setState((s) => ({ ...s, generating: true, generationElapsed: 0, generationParams: null }));
            showToast("Got it — regenerating...");
            break;

          case "thinking":
            setState((s) => ({ ...s, generating: true, generationElapsed: 0 }));
            break;

          case "toast":
            showToast(msg.data.message);
            break;

          case "error":
            setState((s) => ({ ...s, error: msg.data.message }));
            setTimeout(() => setState((s) => ({ ...s, error: null })), 5000);
            break;

          case "radio_switched":
            setState((s) => ({
              ...s,
              radioName: msg.data.name,
              isFirstRun: msg.data.is_new,
              nowPlaying: null,
              generating: false,
            }));
            break;

          case "first_run":
            setState((s) => ({ ...s, isFirstRun: true }));
            break;

          case "reaction_feedback":
            if (msg.data.signal === "liked") showToast("Liked!");
            else if (msg.data.signal === "disliked") showToast("Disliked — changing direction...");
            else if (msg.data.signal === "skipped") showToast("Skipped");
            break;

          case "disk_full":
            showToast(`Storage full (${msg.data.free_mb}MB left)`);
            break;

          case "sleep_expired":
            audioRef.current?.pause();
            showToast("Sleep timer expired");
            break;
        }
      },
      onOpen: () => setState((s) => ({ ...s, connected: true })),
      onClose: () => setState((s) => ({ ...s, connected: false })),
    });

    socketRef.current = socket;
    return () => socket.close();
  }, [showToast]);

  const send = useCallback(
    (type: string, data?: Record<string, any>) => socketRef.current?.send(type, data),
    []
  );

  const start = useCallback(async () => {
    started.current = true;
    const np = nowPlayingRef.current;
    if (np?.audio_url) {
      await audioRef.current?.playTrack(np.audio_url, serverElapsedRef.current || 0);
      audioRef.current?.setupMediaSession({
        title: np.tags || "Personal Radio",
        artist: `${np.bpm || "?"} BPM`,
        onPlay: () => send("resume"),
        onPause: () => send("pause"),
        onNextTrack: () => send("skip"),
      });
    }
  }, [send]);

  const togglePause = useCallback(() => {
    if (audioRef.current?.paused) {
      audioRef.current.resume();
      send("resume");
    } else {
      audioRef.current?.pause();
      send("pause");
    }
  }, [send]);

  const setVolume = useCallback(
    (level: number) => {
      if (audioRef.current) audioRef.current.volume = level / 100;
      setState((s) => ({ ...s, volume: level }));
      send("volume", { level });
    },
    [send]
  );

  const seekDelta = useCallback(
    (delta: number) => {
      audioRef.current?.seekDelta(delta);
      send("seek", { delta });
    },
    [send]
  );

  const seekTo = useCallback((time: number) => {
    audioRef.current?.seek(time);
  }, []);

  return { state, start, started: started.current, send, togglePause, setVolume, seekDelta, seekTo };
}
