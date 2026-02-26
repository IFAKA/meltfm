/**
 * Transport controls — dislike / pause / skip / like + volume slider.
 */
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { X, Play, Pause, SkipForward, Heart, Bookmark, Volume2, RotateCcw } from "lucide-react";

type Props = {
  isPlaying: boolean;
  generating: boolean;
  volume: number;
  onTogglePause: () => void;
  onSkip: () => void;
  onLike: () => void;
  onDislike: () => void;
  onSave: () => void;
  onVolumeChange: (level: number) => void;
  onCleanData: () => void;
};

export default function Controls({
  isPlaying,
  generating,
  volume,
  onTogglePause,
  onSkip,
  onLike,
  onDislike,
  onSave,
  onVolumeChange,
  onCleanData,
}: Props) {
  return (
    <div className="px-6 py-3 shrink-0">
      {/* Main transport */}
      <div className="flex items-center justify-center gap-6 mb-3">
        <Button
          variant="ghost"
          size="icon-lg"
          onClick={onSave}
          className="text-neutral-400 hover:text-skip hover:bg-transparent active:scale-90 transition-all"
          title="Save to favorites"
        >
          <Bookmark className="size-5" />
        </Button>

        <Button
          variant="ghost"
          size="icon-lg"
          onClick={onDislike}
          className="text-neutral-400 hover:text-dislike hover:bg-transparent active:scale-90 transition-all"
          title="Dislike"
        >
          <X className="size-6" />
        </Button>

        <Button
          onClick={onTogglePause}
          className="size-14 rounded-full bg-white! text-black hover:bg-white/90! active:scale-90 transition-transform"
          title={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? <Pause className="size-6" /> : <Play className="size-6" />}
        </Button>

        <Button
          variant="ghost"
          size="icon-lg"
          onClick={onSkip}
          disabled={generating}
          className="text-neutral-400 hover:text-white hover:bg-transparent active:scale-90 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          title={generating ? "Generating next track…" : "Skip"}
        >
          <SkipForward className="size-6" />
        </Button>

        <Button
          variant="ghost"
          size="icon-lg"
          onClick={onLike}
          className="text-neutral-400 hover:text-like hover:bg-transparent active:scale-90 transition-all"
          title="Like"
        >
          <Heart className="size-6" />
        </Button>
      </div>

      {/* Secondary actions */}
      <div className="flex justify-center mb-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={onCleanData}
          className="text-neutral-500 hover:text-dislike hover:bg-transparent"
          title="Clear all data"
        >
          <RotateCcw className="size-3.5" />
          Clear data
        </Button>
      </div>

      {/* Volume */}
      <div className="flex items-center gap-3 px-2">
        <Volume2 className="size-4 text-neutral-500 shrink-0" />
        <Slider
          value={[volume]}
          min={0}
          max={100}
          step={1}
          onValueChange={([val]) => onVolumeChange(val)}
          className="flex-1"
        />
        <span className="text-xs text-neutral-500 w-8 text-right">{volume}%</span>
      </div>
    </div>
  );
}
