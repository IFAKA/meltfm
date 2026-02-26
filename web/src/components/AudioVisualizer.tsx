import { useRef, useEffect } from "react";

const BAR_COUNT = 14;

// Frequency bin range to visualise (bin 2 ≈ 344 Hz, bin 80 ≈ 13.8 kHz at 44100 Hz / fftSize 256)
const START_BIN = 2;
const END_BIN = 80;

// Per-bar bin ranges (linear split across START_BIN..END_BIN)
const BAR_BINS = Array.from({ length: BAR_COUNT }, (_, i) => ({
  start: Math.round(START_BIN + (i / BAR_COUNT) * (END_BIN - START_BIN)),
  end:   Math.round(START_BIN + ((i + 1) / BAR_COUNT) * (END_BIN - START_BIN)),
}));

// Fallback animation parameters (used when analyser isn't available)
const BARS = Array.from({ length: BAR_COUNT }, (_, i) => {
  const pos = i / (BAR_COUNT - 1);
  return {
    phase:  (i * 2.39996) % (Math.PI * 2),
    speed:  1.1 + (i % 5) * 0.65,
    energy: Math.sin(pos * Math.PI) * 0.6 + 0.4,
    idleH:  0.06 + (i % 4) * 0.025,
  };
});

const W_PX = 112;
const H_PX = 28;

interface Props {
  isPlaying: boolean;
  getAnalyser: () => AnalyserNode | null;
}

export default function AudioVisualizer({ isPlaying, getAnalyser }: Props) {
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const frameRef     = useRef(0);
  const ampRef       = useRef(0);
  const isPlayingRef = useRef(isPlaying);
  const startRef     = useRef(performance.now());
  const analyserRef  = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array<ArrayBuffer> | null>(null);

  useEffect(() => { isPlayingRef.current = isPlaying; }, [isPlaying]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Initialise analyser (may be null until first playTrack call, falls back to math)
    const an = getAnalyser();
    if (an) {
      analyserRef.current  = an;
      dataArrayRef.current = new Uint8Array(an.frequencyBinCount) as Uint8Array<ArrayBuffer>;
    }

    // HiDPI / retina
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    canvas.width  = W_PX * dpr;
    canvas.height = H_PX * dpr;
    canvas.style.width  = `${W_PX}px`;
    canvas.style.height = `${H_PX}px`;

    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);

    const barW  = Math.floor((W_PX - (BAR_COUNT - 1)) / BAR_COUNT);
    const radius = Math.min(2, barW / 2);

    function draw() {
      const t = (performance.now() - startRef.current) / 1000;

      // Amplitude envelope — ease in when playing, ease out when stopping
      const target = isPlayingRef.current ? 1 : 0;
      const rate   = isPlayingRef.current ? 0.055 : 0.03;
      ampRef.current += (target - ampRef.current) * rate;
      const amp = ampRef.current;

      // Snapshot frequency data once per frame
      let freqData: Uint8Array | null = null;
      if (analyserRef.current && dataArrayRef.current) {
        analyserRef.current.getByteFrequencyData(dataArrayRef.current);
        freqData = dataArrayRef.current;
      }

      ctx.clearRect(0, 0, W_PX, H_PX);

      BARS.forEach((bar, i) => {
        let level: number;

        if (freqData) {
          // Real audio — average the frequency bins assigned to this bar
          const { start, end } = BAR_BINS[i];
          let sum = 0;
          for (let b = start; b < end; b++) sum += freqData[b];
          level = sum / Math.max(1, end - start) / 255;
        } else {
          // Math fallback (no analyser yet)
          const n1 = Math.sin(t * bar.speed + bar.phase);
          const n2 = Math.sin(t * bar.speed * 1.83 + bar.phase + 1.1) * 0.32;
          level = ((n1 + n2) / 1.32 + 1) / 2;
        }

        const heightFactor = bar.idleH + level * bar.energy * amp * 0.9;
        const barH = Math.max(3, heightFactor * H_PX);
        const x    = i * (barW + 1);
        const y    = (H_PX - barH) / 2;

        const alpha = 0.15 + amp * 0.75;
        const grad  = ctx.createLinearGradient(0, y, 0, y + barH);
        grad.addColorStop(0,   `rgba(56, 222, 246, ${Math.min(1, alpha + 0.12)})`);
        grad.addColorStop(0.5, `rgba(34, 211, 238, ${alpha})`);
        grad.addColorStop(1,   `rgba(8,  145, 178, ${alpha * 0.55})`);

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.roundRect(x, y, barW, barH, radius);
        ctx.fill();
      });

      frameRef.current = requestAnimationFrame(draw);
    }

    draw();
    return () => cancelAnimationFrame(frameRef.current);
  }, []); // intentionally empty — loop reads refs, never restarts

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="block"
    />
  );
}
