/**
 * Now playing — tags, metadata, progress bar (shadcn Slider).
 */
import type { NowPlaying as NowPlayingType } from "@/hooks/useRadio";
import { Slider } from "@/components/ui/slider";
import { Mic } from "lucide-react";

type Props = {
  track: NowPlayingType | null;
  elapsed: number;
  duration: number;
  onSeek: (time: number) => void;
  onShowLyrics?: () => void;
};

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function NowPlaying({ track, elapsed, duration, onSeek, onShowLyrics }: Props) {
  if (!track) {
    return (
      <div className="px-6 py-8 text-center text-neutral-500">
        Waiting for first track...
      </div>
    );
  }

  const tags = track.tags || "generating...";
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

      {/* Progress slider — large touch target on mobile */}
      <Slider
        value={[elapsed]}
        min={0}
        max={duration > 0 ? duration : 1}
        step={0.5}
        onValueChange={([val]) => onSeek(val)}
        className="w-full mb-2"
      />

      {/* Times + lyrics button */}
      <div className="flex justify-between items-center text-xs text-neutral-500">
        <span>{fmtTime(elapsed)}</span>

        {/* Lyrics button — vocal tracks only */}
        {!track.instrumental && track.lyrics && onShowLyrics && (
          <button
            onClick={onShowLyrics}
            className="flex items-center gap-1 text-neutral-500 hover:text-white transition-colors active:scale-95"
            title="Show lyrics"
          >
            <Mic className="size-3" />
            <span>Lyrics</span>
          </button>
        )}

        <span>{duration > 0 ? fmtTime(duration) : "--:--"}</span>
      </div>
    </div>
  );
}
