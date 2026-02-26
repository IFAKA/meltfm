/**
 * LyricsView — Spotify-like full-screen lyrics overlay.
 *
 * Since ACE-Step generates audio from lyrics but we have no word-level
 * timestamps, we estimate the current line by distributing content lines
 * proportionally across the track duration (with a small leading gap).
 */
import { useEffect, useRef, useMemo } from "react";
import { ChevronDown } from "lucide-react";

type Props = {
  show: boolean;
  lyrics: string;
  elapsed: number;
  duration: number;
  trackTags: string;
  onClose: () => void;
};

type SectionLine = { kind: "section"; text: string };
type ContentLine = { kind: "content"; text: string; lineIndex: number };
type ParsedLine = SectionLine | ContentLine;

function parseLyrics(raw: string): ParsedLine[] {
  const out: ParsedLine[] = [];
  let lineIndex = 0;
  for (const line of raw.split("\n")) {
    const t = line.trim();
    if (!t) continue;
    if (/^\[.+\]$/.test(t)) {
      out.push({ kind: "section", text: t.slice(1, -1) });
    } else {
      out.push({ kind: "content", text: t, lineIndex: lineIndex++ });
    }
  }
  return out;
}

export default function LyricsView({ show, lyrics, elapsed, duration, trackTags, onClose }: Props) {
  const lines = useMemo(() => parseLyrics(lyrics), [lyrics]);
  const totalLines = useMemo(() => lines.filter(l => l.kind === "content").length, [lines]);

  // Distribute content lines across ~94% of track duration (skip first/last ~3%)
  const progress = duration > 0
    ? Math.max(0, Math.min(1, (elapsed - duration * 0.03) / (duration * 0.94)))
    : 0;
  const currentLineIndex = Math.min(Math.floor(progress * totalLines), totalLines - 1);

  const lineRefs = useRef<(HTMLDivElement | null)[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to current line
  useEffect(() => {
    if (!show) return;
    const el = lineRefs.current[currentLineIndex];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [currentLineIndex, show]);

  // Reset scroll when a new track loads
  useEffect(() => {
    if (show && scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [lyrics]);

  return (
    <div
      className={[
        "fixed inset-0 z-50 bg-black flex flex-col select-none",
        "transition-transform duration-500 ease-in-out",
        show ? "translate-y-0" : "translate-y-full",
      ].join(" ")}
      aria-hidden={!show}
    >
      {/* Drag handle + close */}
      <button
        onClick={onClose}
        className="shrink-0 flex flex-col items-center pt-3 pb-1 gap-1 touch-none"
        aria-label="Close lyrics"
      >
        <div className="w-9 h-1 rounded-full bg-white/20" />
        <ChevronDown className="size-5 text-white/25 mt-0.5" />
      </button>

      {/* Track label */}
      <p className="shrink-0 text-center text-[11px] text-white/25 uppercase tracking-widest px-8 pb-1 truncate">
        Lyrics · {trackTags.split(",").slice(0, 3).join(", ")}
      </p>

      {/* Scroll container */}
      <div className="relative flex-1 min-h-0">
        <div ref={scrollRef} className="h-full overflow-y-auto px-8">
          {/* Top padding so first line can appear centered */}
          <div className="h-[35vh]" />

          {lines.map((line, i) => {
            if (line.kind === "section") {
              return (
                <p
                  key={i}
                  className="text-[11px] text-white/20 uppercase tracking-[0.15em] font-semibold mb-2 mt-8"
                >
                  {line.text}
                </p>
              );
            }

            const { lineIndex, text } = line;
            const isCurrent = lineIndex === currentLineIndex;
            const isPast = lineIndex < currentLineIndex;

            return (
              <div
                key={i}
                ref={el => { lineRefs.current[lineIndex] = el; }}
                className={[
                  "font-bold leading-tight mb-5",
                  "transition-all duration-700 ease-out",
                  isCurrent
                    ? "text-white text-[1.75rem] scale-[1.03] origin-left"
                    : isPast
                    ? "text-white/25 text-2xl"
                    : "text-white/45 text-2xl",
                ].join(" ")}
              >
                {text}
              </div>
            );
          })}

          {/* Bottom padding */}
          <div className="h-[40vh]" />
        </div>

        {/* Fade gradients */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-black to-transparent" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-black to-transparent" />
      </div>
    </div>
  );
}
