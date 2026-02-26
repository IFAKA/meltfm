/**
 * LyricsView — Spotify-like full-screen lyrics overlay.
 *
 * Only renders when lyricsTimestamps is available (exact Whisper transcription).
 * The lyrics button is only shown once timestamps arrive, so this component
 * never needs a fallback — it always has real data.
 */
import { useEffect, useRef, useMemo } from "react";
import { ChevronDown } from "lucide-react";
import type { LyricsTimestamp } from "../hooks/useRadio";

type Props = {
  show: boolean;
  trackId: string;
  elapsed: number;
  trackTags: string;
  onClose: () => void;
  lyricsTimestamps: LyricsTimestamp[];
};

export default function LyricsView({ show, trackId, elapsed, trackTags, onClose, lyricsTimestamps }: Props) {
  // currentLineIndex: segment actively being sung (-1 = none).
  // pivotIndex: last segment that has started — used to split past/future when
  //             currentLineIndex is -1 (in a gap: segments ≤ pivot are "past").
  const { currentLineIndex, pivotIndex } = useMemo(() => {
    for (let i = lyricsTimestamps.length - 1; i >= 0; i--) {
      const ts = lyricsTimestamps[i];
      if (ts.start === null || elapsed < ts.start) continue;
      // elapsed >= ts.start — this is the latest segment that has started.
      // If ts.end is set and elapsed is past it, check if we're in a gap.
      if (ts.end !== null && elapsed >= ts.end) {
        const nextStart = lyricsTimestamps[i + 1]?.start;
        if (nextStart != null && elapsed < nextStart) {
          // In a gap: segment i has ended, segment i+1 hasn't started yet.
          return { currentLineIndex: -1, pivotIndex: i };
        }
      }
      return { currentLineIndex: i, pivotIndex: i };
    }
    return { currentLineIndex: -1, pivotIndex: -1 };
  }, [elapsed, lyricsTimestamps]);

  const lineRefs = useRef<(HTMLDivElement | null)[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Reset refs and scroll position when a new track's timestamps arrive
  useEffect(() => {
    lineRefs.current = [];
    if (show && scrollRef.current) scrollRef.current.scrollTop = 0;
  }, [trackId]);

  // Auto-scroll to current line
  useEffect(() => {
    if (!show || currentLineIndex < 0) return;
    const el = lineRefs.current[currentLineIndex];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [currentLineIndex, show]);

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
          <div className="h-[35vh]" />

          {lyricsTimestamps.map((ts, i) => {
            const isCurrent = i === currentLineIndex;
            // During a gap (currentLineIndex = -1), segments up to pivotIndex are past.
            const isPast = currentLineIndex >= 0 ? i < currentLineIndex : i <= pivotIndex;
            return (
              <div
                key={i}
                ref={el => { lineRefs.current[i] = el; }}
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
                {ts.text}
              </div>
            );
          })}

          <div className="h-[40vh]" />
        </div>

        {/* Fade gradients */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-black to-transparent" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-black to-transparent" />
      </div>
    </div>
  );
}
