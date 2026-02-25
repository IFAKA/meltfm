/**
 * Now playing — tags, metadata, progress bar.
 */
import type { NowPlaying as NowPlayingType } from "../hooks/useRadio";

type Props = {
  track: NowPlayingType | null;
  elapsed: number;
  duration: number;
  onSeek: (time: number) => void;
};

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function NowPlaying({ track, elapsed, duration, onSeek }: Props) {
  if (!track) {
    return (
      <div className="px-6 py-8 text-center text-neutral-500">
        Waiting for first track...
      </div>
    );
  }

  const tags = track.tags || "generating...";
  const progress = duration > 0 ? (elapsed / duration) * 100 : 0;

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (duration <= 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    onSeek(pct * duration);
  };

  const ts = track.time_signature || 4;
  const mode = track.instrumental ? "instrumental" : "vocal";

  return (
    <div className="px-6 py-4">
      {/* Tags */}
      <div className="text-lg font-semibold leading-snug mb-1">{tags}</div>

      {/* Metadata */}
      <div className="text-sm text-neutral-400 mb-4">
        {track.bpm} BPM &middot; {track.key_scale} &middot; {ts}/4 &middot; {mode}
      </div>

      {/* Rationale */}
      {track.rationale && (
        <div className="text-sm text-neutral-500 italic mb-4">
          &ldquo;{track.rationale}&rdquo;
        </div>
      )}

      {/* Progress bar */}
      <div
        className="w-full h-1.5 bg-neutral-700 rounded-full cursor-pointer mb-1 relative"
        onClick={handleProgressClick}
      >
        <div
          className="h-full bg-accent rounded-full transition-[width] duration-300"
          style={{ width: `${Math.min(100, progress)}%` }}
        />
      </div>

      {/* Times */}
      <div className="flex justify-between text-xs text-neutral-500">
        <span>{fmtTime(elapsed)}</span>
        <span>{duration > 0 ? fmtTime(duration) : "--:--"}</span>
      </div>
    </div>
  );
}
