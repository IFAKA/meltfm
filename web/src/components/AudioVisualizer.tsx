import { useRef, useEffect } from "react";

const BAR_COUNT = 14;

// Deterministic per-bar parameters (golden angle phase distribution)
const BARS = Array.from({ length: BAR_COUNT }, (_, i) => {
  const pos = i / (BAR_COUNT - 1);
  return {
    phase: (i * 2.39996) % (Math.PI * 2),       // golden angle spread
    speed: 1.1 + (i % 5) * 0.65,                 // unique frequency per bar
    energy: Math.sin(pos * Math.PI) * 0.6 + 0.4, // bell curve — more energy in middle
    idleH: 0.06 + (i % 4) * 0.025,               // tiny idle height
  };
});

const W_PX = 112;
const H_PX = 28;

export default function AudioVisualizer({ isPlaying }: { isPlaying: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(0);
  const ampRef = useRef(0);
  const isPlayingRef = useRef(isPlaying);
  const startRef = useRef(performance.now());

  // Keep ref in sync so the RAF loop doesn't need to restart on prop changes
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // HiDPI / retina support
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    canvas.width = W_PX * dpr;
    canvas.height = H_PX * dpr;
    canvas.style.width = `${W_PX}px`;
    canvas.style.height = `${H_PX}px`;

    const ctx = canvas.getContext("2d")!;
    ctx.scale(dpr, dpr);

    const barW = Math.floor((W_PX - (BAR_COUNT - 1)) / BAR_COUNT);
    const radius = Math.min(2, barW / 2);

    function draw() {
      const t = (performance.now() - startRef.current) / 1000;

      // Smoothly track playing state (ease-in when starting, ease-out when stopping)
      const target = isPlayingRef.current ? 1 : 0;
      const rate = isPlayingRef.current ? 0.055 : 0.03;
      ampRef.current += (target - ampRef.current) * rate;
      const amp = ampRef.current;

      ctx.clearRect(0, 0, W_PX, H_PX);

      BARS.forEach((bar, i) => {
        // Two layered sines for organic, non-mechanical feel
        const n1 = Math.sin(t * bar.speed + bar.phase);
        const n2 = Math.sin(t * bar.speed * 1.83 + bar.phase + 1.1) * 0.32;
        const noise = ((n1 + n2) / 1.32 + 1) / 2; // normalize to 0..1

        const heightFactor = bar.idleH + noise * bar.energy * amp * 0.9;
        const barH = Math.max(3, heightFactor * H_PX);
        const x = i * (barW + 1);
        const y = (H_PX - barH) / 2;

        // Cyan gradient — brighter at top, deeper at bottom
        const alpha = 0.15 + amp * 0.75;
        const grad = ctx.createLinearGradient(0, y, 0, y + barH);
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
