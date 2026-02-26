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

/** Which phase of the generation pipeline is active. */
export type PipelineStage = "idle" | "waiting" | "thinking" | "generating" | "ready" | "error";

export type PipelineState = {
  stage: PipelineStage;
  llmDone: boolean;       // LLM params received (ACE-Step may still be running)
  warnings: string[];     // warnings from last LLM call
  lastError: string | null;
};

export type EventEntry = {
  id: number;
  ts: number;   // Date.now()
  type: string;
  summary: string;
  level: "info" | "warn" | "error";
  payload?: Record<string, unknown>;
  deltaMs?: number;
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
  queueReady: boolean;  // true = next track is generated and queued, waiting to play
  generationElapsed: number;
  generationParams: Record<string, unknown> | null;
  error: string | null;
  pipeline: PipelineState;
  events: EventEntry[];
  llmDurationMs: number | null;
  aceDurationMs: number | null;
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
    queueReady: false,
    generationElapsed: 0,
    generationParams: null,
    error: null,
    pipeline: { stage: "idle", llmDone: false, warnings: [], lastError: null },
    events: [],
    llmDurationMs: null,
    aceDurationMs: null,
  });

  const socketRef = useRef<RadioSocket | null>(null);
  const audioRef = useRef<AudioManager | null>(null);
  const started = useRef(false);
  // Refs to avoid stale closures in start()
  const nowPlayingRef = useRef<NowPlaying | null>(null);
  const serverElapsedRef = useRef(0);
  const eventIdRef = useRef(0);
  // Tracks whether now_playing fired after the current generation_start.
  // Used to distinguish "track queued and ready" from "track already playing".
  const nowPlayingAfterGenStart = useRef(false);
  // Timing refs for LLM and ACE-Step durations
  const lastEventTsRef = useRef<number | null>(null);
  const thinkingStartRef = useRef<number | null>(null);
  const genStartRef = useRef<number | null>(null);
  // Track last progress milestone logged (in seconds)
  const lastProgressMilestoneRef = useRef(0);

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

    /** Create a typed event log entry with optional payload and delta time. */
    const mkEvent = (
      type: string,
      summary: string,
      level: EventEntry["level"],
      payload?: Record<string, unknown>
    ): EventEntry => {
      const now = Date.now();
      const deltaMs = lastEventTsRef.current != null ? now - lastEventTsRef.current : undefined;
      lastEventTsRef.current = now;
      return {
        id: ++eventIdRef.current,
        ts: now,
        type,
        summary,
        level,
        payload,
        deltaMs,
      };
    };

    const pushEvent = (e: EventEntry) =>
      setState((s) => ({ ...s, events: [e, ...s.events].slice(0, 60) }));

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

          case "now_playing": {
            const np = msg.data as NowPlaying;
            const tag0 = np.tags?.split(",")[0]?.trim() ?? "track";
            const npEvt = mkEvent(
              "now_playing",
              `▶ ${tag0}${np.bpm ? " · " + np.bpm + " BPM" : ""}`,
              "info",
              { id: np.id, tags: np.tags, bpm: np.bpm, key_scale: np.key_scale, instrumental: np.instrumental, rationale: np.rationale }
            );
            nowPlayingRef.current = np;
            nowPlayingAfterGenStart.current = true;
            setState((s) => ({
              ...s,
              nowPlaying: np,
              queueReady: false,
              generationParams: null,
              pipeline: { ...s.pipeline, stage: "idle", llmDone: false },
              events: [npEvt, ...s.events].slice(0, 60),
            }));
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
          }

          case "playback_state":
            // Only sync volume — play/pause state is owned by audio element
            setState((s) => ({ ...s, volume: msg.data.volume ?? s.volume }));
            break;

          case "tick":
            serverElapsedRef.current = msg.data.elapsed;
            break;

          case "thinking": {
            thinkingStartRef.current = Date.now();
            const evt = mkEvent("thinking", "LLM thinking…", "info");
            setState((s) => ({
              ...s,
              generating: true,
              generationElapsed: 0,
              pipeline: { stage: "thinking", llmDone: false, warnings: [], lastError: null },
              events: [evt, ...s.events].slice(0, 60),
            }));
            break;
          }

          case "generation_start": {
            const p = msg.data.params as Record<string, unknown>;
            const tag0 = typeof p?.tags === "string" ? p.tags.split(",")[0]?.trim() : "?";
            const bpmStr = typeof p?.bpm === "number" ? `${p.bpm} BPM` : "";
            const warnings: string[] = Array.isArray(msg.data.warnings) ? msg.data.warnings : [];
            const level: EventEntry["level"] = warnings.length > 0 ? "warn" : "info";
            // Compute LLM duration
            const llmDurationMs = thinkingStartRef.current != null
              ? Date.now() - thinkingStartRef.current
              : null;
            genStartRef.current = Date.now();
            lastProgressMilestoneRef.current = 0;
            const evt = mkEvent(
              "generation_start",
              `ACE-Step: ${tag0}${bpmStr ? " · " + bpmStr : ""}`,
              level,
              { params: p, warnings }
            );
            nowPlayingAfterGenStart.current = false;
            setState((s) => ({
              ...s,
              generating: true,
              queueReady: false,
              generationElapsed: 0,
              generationParams: msg.data.params,
              pipeline: { stage: "generating", llmDone: true, warnings, lastError: null },
              events: [evt, ...s.events].slice(0, 60),
              llmDurationMs: llmDurationMs ?? s.llmDurationMs,
            }));
            break;
          }

          case "generation_progress": {
            const elapsed: number = msg.data.elapsed ?? 0;
            // Log milestone every 15s
            const milestone = Math.floor(elapsed / 15) * 15;
            if (milestone > 0 && milestone > lastProgressMilestoneRef.current) {
              lastProgressMilestoneRef.current = milestone;
              const evt = mkEvent(
                "generation_progress",
                `ACE-Step: ${milestone}s elapsed`,
                "info",
                { elapsed }
              );
              setState((s) => ({
                ...s,
                generationElapsed: elapsed,
                events: [evt, ...s.events].slice(0, 60),
              }));
            } else {
              setState((s) => ({ ...s, generationElapsed: elapsed }));
            }
            break;
          }

          case "generation_done": {
            // If now_playing fired after generation_start, the track is already playing
            // (immediate play on first track or auto-advance). Otherwise it's queued and ready.
            const isQueued = !nowPlayingAfterGenStart.current;
            const aceDurationMs = genStartRef.current != null
              ? Date.now() - genStartRef.current
              : null;
            const evt = mkEvent(
              "generation_done",
              isQueued ? "Track queued — ready to play" : "Track ready",
              "info",
              { queued: isQueued }
            );
            setState((s) => ({
              ...s,
              generating: false,
              queueReady: isQueued,
              generationElapsed: 0,
              // Keep generationParams when queued so the badge can show track info
              generationParams: isQueued ? s.generationParams : null,
              pipeline: { ...s.pipeline, stage: isQueued ? "ready" : "idle" },
              events: [evt, ...s.events].slice(0, 60),
              aceDurationMs: aceDurationMs ?? s.aceDurationMs,
            }));
            break;
          }

          case "regenerating": {
            const evt = mkEvent(
              "regenerating",
              `Regenerating: "${msg.data.reason}"`,
              "warn",
              { reason: msg.data.reason }
            );
            nowPlayingAfterGenStart.current = false;
            setState((s) => ({
              ...s,
              generating: true,
              queueReady: false,
              generationElapsed: 0,
              generationParams: null,
              pipeline: { stage: "thinking", llmDone: false, warnings: [], lastError: null },
              events: [evt, ...s.events].slice(0, 60),
            }));
            showToast("Got it — regenerating...");
            break;
          }

          case "toast":
            showToast(msg.data.message);
            break;

          case "error": {
            const errMsg: string = msg.data.message;
            const evt = mkEvent("error", errMsg, "error", { message: errMsg });
            setState((s) => ({
              ...s,
              error: errMsg,
              pipeline: { ...s.pipeline, stage: "error", lastError: errMsg },
              events: [evt, ...s.events].slice(0, 60),
            }));
            setTimeout(() => setState((s) => ({ ...s, error: null })), 5000);
            break;
          }

          case "radio_switched": {
            const evt = mkEvent("radio_switched", `Switched to: ${msg.data.name}`, "info");
            nowPlayingAfterGenStart.current = false;
            setState((s) => ({
              ...s,
              radioName: msg.data.name,
              isFirstRun: msg.data.is_new,
              nowPlaying: null,
              generating: false,
              queueReady: false,
              generationParams: null,
              pipeline: { stage: "idle", llmDone: false, warnings: [], lastError: null },
              events: [evt, ...s.events].slice(0, 60),
            }));
            break;
          }

          case "first_run":
            setState((s) => ({ ...s, isFirstRun: true }));
            break;

          case "reaction_feedback": {
            const sig = msg.data.signal;
            if (sig === "liked") {
              showToast("Liked!");
              pushEvent(mkEvent("reaction_feedback", "♥ Liked", "info"));
            } else if (sig === "disliked") {
              showToast("Disliked — changing direction...");
              pushEvent(mkEvent("reaction_feedback", "✕ Disliked", "warn"));
            } else if (sig === "skipped") {
              showToast("Skipped");
              pushEvent(mkEvent("reaction_feedback", "» Skipped", "info"));
            }
            break;
          }

          case "disk_full": {
            showToast(`Storage full (${msg.data.free_mb}MB left)`);
            pushEvent(mkEvent("disk_full", `Disk full (${msg.data.free_mb}MB free)`, "error", { free_mb: msg.data.free_mb }));
            break;
          }

          case "sleep_expired":
            audioRef.current?.pause();
            showToast("Sleep timer expired");
            break;

          case "waiting": {
            const waitMsg: string = msg.data.message || "Waiting…";
            setState((s) => ({
              ...s,
              generating: true,
              pipeline: { stage: "waiting", llmDone: false, warnings: [], lastError: waitMsg },
            }));
            break;
          }
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
