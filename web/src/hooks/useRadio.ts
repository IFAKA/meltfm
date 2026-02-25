/**
 * useRadio — main hook connecting WebSocket state + audio playback.
 */
import { useCallback, useEffect, useRef, useState } from "react";
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

export type PlaybackState = {
  playing: boolean;
  paused: boolean;
  elapsed: number;
  duration: number | null;
  volume: number;
  has_track: boolean;
};

export type RadioState = {
  connected: boolean;
  radioName: string;
  isFirstRun: boolean;
  nowPlaying: NowPlaying | null;
  playback: PlaybackState;
  generating: boolean;
  generationElapsed: number;
  generationParams: Record<string, any> | null;
  toast: string | null;
  error: string | null;
  // Local audio state (more accurate than server ticks)
  localElapsed: number;
  localDuration: number;
};

const DEFAULT_PLAYBACK: PlaybackState = {
  playing: false,
  paused: false,
  elapsed: 0,
  duration: null,
  volume: 80,
  has_track: false,
};

export function useRadio() {
  const [state, setState] = useState<RadioState>({
    connected: false,
    radioName: "default",
    isFirstRun: true,
    nowPlaying: null,
    playback: DEFAULT_PLAYBACK,
    generating: false,
    generationElapsed: 0,
    generationParams: null,
    toast: null,
    error: null,
    localElapsed: 0,
    localDuration: 0,
  });

  const socketRef = useRef<RadioSocket | null>(null);
  const audioRef = useRef<AudioManager | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const started = useRef(false);

  // Clear toast after 3s
  const showToast = useCallback((msg: string) => {
    setState((s) => ({ ...s, toast: msg }));
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => {
      setState((s) => ({ ...s, toast: null }));
    }, 3000);
  }, []);

  // Initialize audio manager
  useEffect(() => {
    const audio = new AudioManager({
      onTimeUpdate: (elapsed, duration) => {
        setState((s) => ({
          ...s,
          localElapsed: elapsed,
          localDuration: duration,
        }));
      },
      onEnded: () => {
        socketRef.current?.send("track_ended");
      },
      onError: () => {
        showToast("Track unavailable — skipping...");
        setTimeout(() => socketRef.current?.send("skip"), 3000);
      },
    });
    audioRef.current = audio;
    return () => audio.destroy();
  }, [showToast]);

  // Initialize WebSocket
  useEffect(() => {
    const socket = new RadioSocket({
      onMessage: (msg) => {
        switch (msg.type) {
          case "sync":
            setState((s) => ({
              ...s,
              radioName: msg.data.radio_name,
              isFirstRun: msg.data.is_first_run,
              nowPlaying: msg.data.now_playing,
              playback: msg.data.playback || DEFAULT_PLAYBACK,
              generating: msg.data.generating,
            }));
            // If there's a track playing on server, play it in browser
            if (msg.data.now_playing?.audio_url && started.current) {
              audioRef.current?.playTrack(
                msg.data.now_playing.audio_url,
                msg.data.playback?.elapsed || 0
              );
            }
            break;

          case "now_playing":
            setState((s) => ({ ...s, nowPlaying: msg.data }));
            if (started.current && msg.data.audio_url) {
              // Use crossfade if already playing
              if (audioRef.current?.hasSource && !audioRef.current?.paused) {
                audioRef.current?.crossfadeTo(msg.data.audio_url);
              } else {
                audioRef.current?.playTrack(msg.data.audio_url);
              }
              // Update media session
              const tags = msg.data.tags || "Personal Radio";
              audioRef.current?.setupMediaSession({
                title: tags,
                artist: `${msg.data.bpm || "?"} BPM - ${msg.data.key_scale || "?"}`,
                onPlay: () => socketRef.current?.send("resume"),
                onPause: () => socketRef.current?.send("pause"),
                onNextTrack: () => socketRef.current?.send("skip"),
              });
            }
            break;

          case "playback_state":
            setState((s) => ({ ...s, playback: msg.data }));
            break;

          case "tick":
            // Server tick — we use local audio time, but update server state
            setState((s) => ({
              ...s,
              playback: { ...s.playback, elapsed: msg.data.elapsed, duration: msg.data.duration },
            }));
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
            setState((s) => ({
              ...s,
              generationElapsed: msg.data.elapsed,
            }));
            break;

          case "generation_done":
            setState((s) => ({
              ...s,
              generating: false,
              generationElapsed: 0,
              generationParams: null,
            }));
            break;

          case "regenerating":
            setState((s) => ({ ...s, generating: true, generationElapsed: 0 }));
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
            // Brief visual feedback
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

  // Actions
  const send = useCallback(
    (type: string, data?: Record<string, any>) => socketRef.current?.send(type, data),
    []
  );

  const start = useCallback(async () => {
    started.current = true;
    // If we already have a track, start playing it
    const np = state.nowPlaying;
    if (np?.audio_url) {
      await audioRef.current?.playTrack(np.audio_url, state.playback.elapsed || 0);
      audioRef.current?.setupMediaSession({
        title: np.tags || "Personal Radio",
        artist: `${np.bpm || "?"} BPM`,
        onPlay: () => send("resume"),
        onPause: () => send("pause"),
        onNextTrack: () => send("skip"),
      });
    }
  }, [state.nowPlaying, state.playback.elapsed, send]);

  const togglePause = useCallback(() => {
    if (audioRef.current?.paused) {
      audioRef.current?.resume();
      send("resume");
    } else {
      audioRef.current?.pause();
      send("pause");
    }
  }, [send]);

  const setVolume = useCallback(
    (level: number) => {
      if (audioRef.current) audioRef.current.volume = level / 100;
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

  const seekTo = useCallback(
    (time: number) => {
      audioRef.current?.seek(time);
    },
    []
  );

  return {
    state,
    start,
    started: started.current,
    send,
    togglePause,
    setVolume,
    seekDelta,
    seekTo,
    audioRef,
  };
}
