/**
 * Never-stop audio manager.
 * Handles playback, crossfade, looping, and fallback.
 */

const CROSSFADE_MS = 500;

export type AudioCallbacks = {
  onTimeUpdate?: (elapsed: number, duration: number) => void;
  onEnded?: () => void;
  onError?: (err: string) => void;
};

export class AudioManager {
  private audio: HTMLAudioElement;
  private fallbackQueue: string[] = [];
  private nextTrackUrl: string | null = null;
  private callbacks: AudioCallbacks;
  private _volume = 0.8;
  private wakeLock: WakeLockSentinel | null = null;

  constructor(callbacks: AudioCallbacks = {}) {
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.callbacks = callbacks;

    this.audio.addEventListener("timeupdate", () => {
      this.callbacks.onTimeUpdate?.(this.audio.currentTime, this.audio.duration || 0);
    });

    this.audio.addEventListener("ended", () => {
      if (this.nextTrackUrl) {
        this.playTrack(this.nextTrackUrl);
        this.nextTrackUrl = null;
      } else {
        // Loop current track
        this.audio.currentTime = 0;
        this.audio.play().catch(() => {});
      }
      this.callbacks.onEnded?.();
    });

    this.audio.addEventListener("error", () => {
      this.callbacks.onError?.("Audio load failed");
      // Try fallback
      this.playFallback();
    });
  }

  async playTrack(url: string, seekTo?: number) {
    this.audio.src = url;
    this.audio.volume = this._volume;
    if (seekTo) this.audio.currentTime = seekTo;
    try {
      await this.audio.play();
      this.fallbackQueue.push(url);
      if (this.fallbackQueue.length > 10) this.fallbackQueue.shift();
      await this.requestWakeLock();
    } catch {
      this.playFallback();
    }
  }

  async crossfadeTo(nextUrl: string) {
    const next = new Audio(nextUrl);
    next.volume = 0;
    next.preload = "auto";

    try {
      await next.play();
    } catch {
      // Crossfade failed — hard switch
      await this.playTrack(nextUrl);
      return;
    }

    const steps = 20;
    const interval = CROSSFADE_MS / steps;
    const baseVol = this._volume;

    for (let i = 0; i <= steps; i++) {
      this.audio.volume = (1 - i / steps) * baseVol;
      next.volume = (i / steps) * baseVol;
      await new Promise((r) => setTimeout(r, interval));
    }

    this.audio.pause();
    this.audio.removeAttribute("src");

    // Transfer event listeners
    this.audio = next;
    this.audio.addEventListener("timeupdate", () => {
      this.callbacks.onTimeUpdate?.(this.audio.currentTime, this.audio.duration || 0);
    });
    this.audio.addEventListener("ended", () => {
      if (this.nextTrackUrl) {
        this.playTrack(this.nextTrackUrl);
        this.nextTrackUrl = null;
      } else {
        this.audio.currentTime = 0;
        this.audio.play().catch(() => {});
      }
      this.callbacks.onEnded?.();
    });
    this.audio.addEventListener("error", () => {
      this.callbacks.onError?.("Audio load failed");
      this.playFallback();
    });

    this.fallbackQueue.push(nextUrl);
    if (this.fallbackQueue.length > 10) this.fallbackQueue.shift();
  }

  setNextTrack(url: string) {
    this.nextTrackUrl = url;
  }

  private playFallback() {
    const prev = this.fallbackQueue.pop();
    if (prev) {
      this.audio.src = prev;
      this.audio.volume = this._volume;
      this.audio.play().catch(() => {});
    }
  }

  pause() {
    this.audio.pause();
  }

  resume() {
    this.audio.play().catch(() => {});
  }

  get paused() {
    return this.audio.paused;
  }

  get currentTime() {
    return this.audio.currentTime;
  }

  get duration() {
    return this.audio.duration || 0;
  }

  set volume(v: number) {
    this._volume = v;
    this.audio.volume = v;
  }

  get volume() {
    return this._volume;
  }

  seek(time: number) {
    this.audio.currentTime = Math.max(0, Math.min(time, this.audio.duration || 0));
  }

  seekDelta(delta: number) {
    this.seek(this.audio.currentTime + delta);
  }

  get hasSource() {
    return !!this.audio.src && this.audio.src !== location.href;
  }

  // Wake Lock — keep screen on during playback
  private async requestWakeLock() {
    if ("wakeLock" in navigator) {
      try {
        this.wakeLock = await navigator.wakeLock.request("screen");
      } catch {
        // Wake lock denied
      }
    }
  }

  // Media Session — lock screen controls
  setupMediaSession(opts: {
    title?: string;
    artist?: string;
    onPlay?: () => void;
    onPause?: () => void;
    onNextTrack?: () => void;
    onPreviousTrack?: () => void;
  }) {
    if (!("mediaSession" in navigator)) return;

    navigator.mediaSession.metadata = new MediaMetadata({
      title: opts.title || "Personal Radio",
      artist: opts.artist || "AI Radio",
    });

    navigator.mediaSession.setActionHandler("play", () => {
      this.resume();
      opts.onPlay?.();
    });
    navigator.mediaSession.setActionHandler("pause", () => {
      this.pause();
      opts.onPause?.();
    });
    navigator.mediaSession.setActionHandler("nexttrack", () => opts.onNextTrack?.());
    navigator.mediaSession.setActionHandler("previoustrack", () => opts.onPreviousTrack?.());
  }

  destroy() {
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.wakeLock?.release().catch(() => {});
  }
}
