/**
 * LyricsView — Spotify-like full-screen lyrics overlay.
 *
 * Since ACE-Step generates audio from lyrics but we have no word-level
 * timestamps, we estimate the current line by distributing content lines
 * proportionally across the track duration. Lines are weighted by word count
 * and section breaks get instrumental gap time to better match real singing.
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

/**
 * Assign an estimated start time (in seconds) to each content line.
 *
 * Strategy:
 *  - Intro gap: 8% of duration before first lyric
 *  - Outro gap: 6% of duration after last lyric
 *  - Section breaks (between sections): 2.5% of duration each
 *  - Remaining time split proportionally by word count (longer lines = more time)
 */
function buildLineTimes(lines: ParsedLine[], duration: number): number[] {
  if (duration <= 0) return lines.map(() => 0);

  const INTRO = duration * 0.08;
  const OUTRO = duration * 0.06;
  const SECTION_BREAK = duration * 0.025;

  // Group content lines into sections
  type Segment = ContentLine[];
  const segments: Segment[] = [];
  let current: Segment = [];
  for (const line of lines) {
    if (line.kind === "section") {
      if (current.length > 0) { segments.push(current); current = []; }
    } else {
      current.push(line);
    }
  }
  if (current.length > 0) segments.push(current);

  const numBreaks = Math.max(0, segments.length - 1);
  const totalBreakTime = numBreaks * SECTION_BREAK;
  const timeForLines = Math.max(0, duration - INTRO - OUTRO - totalBreakTime);

  // Weight each line by word count (min 1)
  const wordCount = (l: ContentLine) => Math.max(1, l.text.split(/\s+/).length);
  const allContent = segments.flat();
  const totalWeight = allContent.reduce((s, l) => s + wordCount(l), 0);

  // Build a map: lineIndex -> start time
  const startTimes = new Map<number, number>();
  let t = INTRO;
  for (let si = 0; si < segments.length; si++) {
    if (si > 0) t += SECTION_BREAK;
    for (const line of segments[si]) {
      startTimes.set(line.lineIndex, t);
      t += (wordCount(line) / totalWeight) * timeForLines;
    }
  }

  // Return flat array indexed by lineIndex
  const totalContent = allContent.length;
  return Array.from({ length: totalContent }, (_, i) => startTimes.get(i) ?? 0);
}

export default function LyricsView({ show, lyrics, elapsed, duration, trackTags, onClose }: Props) {
  const lines = useMemo(() => parseLyrics(lyrics), [lyrics]);
  const totalLines = useMemo(() => lines.filter(l => l.kind === "content").length, [lines]);

  // Estimated start time (seconds) for each content line
  const lineTimes = useMemo(() => buildLineTimes(lines, duration), [lines, duration]);

  // Current line = last line whose start time <= elapsed (or -1 before intro)
  const currentLineIndex = useMemo(() => {
    if (totalLines === 0 || duration <= 0) return -1;
    let idx = -1;
    for (let i = 0; i < totalLines; i++) {
      if (elapsed >= lineTimes[i]) idx = i;
    }
    return idx;
  }, [elapsed, lineTimes, totalLines, duration]);

  const lineRefs = useRef<(HTMLDivElement | null)[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to current line
  useEffect(() => {
    if (!show || currentLineIndex < 0) return;
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
            const isCurrent = currentLineIndex >= 0 && lineIndex === currentLineIndex;
            const isPast = currentLineIndex >= 0 && lineIndex < currentLineIndex;

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
