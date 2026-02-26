/**
 * Never-stop audio manager.
 * Handles playback, crossfade, looping, and fallback.
 */

const CROSSFADE_MS = 500;

export type AudioCallbacks = {
  onTimeUpdate?: (elapsed: number, duration: number) => void;
  onPlayStateChange?: (playing: boolean) => void;
  onEnded?: () => void;
  onError?: (err: string) => void;
};

export class AudioManager {
  private audio: HTMLAudioElement;
  private fallbackQueue: string[] = [];
  private callbacks: AudioCallbacks;
  private _volume = 0.8;
  private wakeLock: WakeLockSentinel | null = null;
  private _suppressNextPause = false;

  // Web Audio API — for real-time frequency analysis
  private audioCtx: AudioContext | null = null;
  private analyserNode: AnalyserNode | null = null;
  private readonly _connectedEls = new WeakSet<HTMLAudioElement>();

  constructor(callbacks: AudioCallbacks = {}) {
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.callbacks = callbacks;
    this._attach(this.audio);
  }

  private _initAudioContext() {
    if (this.audioCtx) return;
    this.audioCtx = new AudioContext();
    this.analyserNode = this.audioCtx.createAnalyser();
    this.analyserNode.fftSize = 256;               // 128 frequency bins
    this.analyserNode.smoothingTimeConstant = 0.75;
    this.analyserNode.connect(this.audioCtx.destination);
  }

  private _connectElement(el: HTMLAudioElement) {
    if (!this.audioCtx || !this.analyserNode) return;
    if (this._connectedEls.has(el)) return;        // can only call createMediaElementSource once per element
    const src = this.audioCtx.createMediaElementSource(el);
    src.connect(this.analyserNode);
    this._connectedEls.add(el);
  }

  get analyser(): AnalyserNode | null {
    return this.analyserNode;
  }

  private _attach(el: HTMLAudioElement) {
    el.addEventListener("timeupdate", () => {
      this.callbacks.onTimeUpdate?.(el.currentTime, el.duration || 0);
    });
    el.addEventListener("play", () => this.callbacks.onPlayStateChange?.(true));
    el.addEventListener("pause", () => {
      if (this._suppressNextPause) { this._suppressNextPause = false; return; }
      this.callbacks.onPlayStateChange?.(false);
    });
    el.addEventListener("ended", () => {
      el.currentTime = 0;
      el.play().catch(() => {});
      this.callbacks.onEnded?.();
    });
    el.addEventListener("error", () => {
      this.callbacks.onError?.("Audio load failed");
      this._playFallback();
    });
  }

  async playTrack(url: string, seekTo?: number) {
    this._initAudioContext();
    this._connectElement(this.audio);
    this.audio.src = url;
    this.audio.volume = this._volume;
    if (seekTo) this.audio.currentTime = seekTo;
    try {
      await this.audio.play();
      this._addFallback(url);
      this._requestWakeLock();
    } catch {
      this._playFallback();
    }
  }

  async crossfadeTo(nextUrl: string) {
    const next = new Audio(nextUrl);
    next.volume = 0;
    next.preload = "auto";

    // Connect to Web Audio graph before playing so frequency data is available
    this._connectElement(next);

    try {
      await next.play();
    } catch {
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

    this._suppressNextPause = true;
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.audio = next;
    this._attach(this.audio);
    // next is already playing; fire manually since 'play' event won't re-fire
    this.callbacks.onPlayStateChange?.(true);
    this._addFallback(nextUrl);
  }

  private _addFallback(url: string) {
    this.fallbackQueue.push(url);
    if (this.fallbackQueue.length > 10) this.fallbackQueue.shift();
  }

  private _playFallback() {
    const prev = this.fallbackQueue.pop();
    if (prev) {
      this.audio.src = prev;
      this.audio.volume = this._volume;
      this.audio.play().catch(() => {});
    }
  }

  pause() { this.audio.pause(); }
  resume() { this.audio.play().catch(() => {}); }

  get paused() { return this.audio.paused; }
  get hasSource() { return !!this.audio.src && this.audio.src !== location.href; }

  set volume(v: number) {
    this._volume = v;
    this.audio.volume = v;
  }

  seek(time: number) {
    this.audio.currentTime = Math.max(0, Math.min(time, this.audio.duration || 0));
  }

  seekDelta(delta: number) { this.seek(this.audio.currentTime + delta); }

  private async _requestWakeLock() {
    if ("wakeLock" in navigator) {
      try { this.wakeLock = await navigator.wakeLock.request("screen"); } catch {}
    }
  }

  setupMediaSession(opts: {
    title?: string;
    artist?: string;
    onPlay?: () => void;
    onPause?: () => void;
    onNextTrack?: () => void;
  }) {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: opts.title || "Personal Radio",
      artist: opts.artist || "AI Radio",
    });
    navigator.mediaSession.setActionHandler("play", () => { this.resume(); opts.onPlay?.(); });
    navigator.mediaSession.setActionHandler("pause", () => { this.pause(); opts.onPause?.(); });
    navigator.mediaSession.setActionHandler("nexttrack", () => opts.onNextTrack?.());
  }

  destroy() {
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.audioCtx?.close();
    this.wakeLock?.release().catch(() => {});
  }
}
