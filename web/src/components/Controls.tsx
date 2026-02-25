/**
 * Transport controls — dislike / pause / skip / like + volume slider.
 */

type Props = {
  playing: boolean;
  volume: number;
  onTogglePause: () => void;
  onSkip: () => void;
  onLike: () => void;
  onDislike: () => void;
  onSave: () => void;
  onVolumeChange: (level: number) => void;
};

export default function Controls({
  playing,
  volume,
  onTogglePause,
  onSkip,
  onLike,
  onDislike,
  onSave,
  onVolumeChange,
}: Props) {
  return (
    <div className="px-6 py-2">
      {/* Main controls */}
      <div className="flex items-center justify-center gap-8 mb-4">
        {/* Dislike */}
        <button
          onClick={onDislike}
          className="text-2xl text-neutral-400 hover:text-dislike active:scale-90 transition-all"
          title="Dislike"
        >
          &#10007;
        </button>

        {/* Play/Pause */}
        <button
          onClick={onTogglePause}
          className="w-14 h-14 rounded-full bg-white text-black flex items-center justify-center text-2xl active:scale-90 transition-transform"
          title={playing ? "Pause" : "Play"}
        >
          {playing ? "\u23F8" : "\u25B6"}
        </button>

        {/* Skip */}
        <button
          onClick={onSkip}
          className="text-2xl text-neutral-400 hover:text-white active:scale-90 transition-all"
          title="Skip"
        >
          &#x23ED;
        </button>

        {/* Like */}
        <button
          onClick={onLike}
          className="text-2xl text-neutral-400 hover:text-like active:scale-90 transition-all"
          title="Like"
        >
          &#9829;
        </button>
      </div>

      {/* Save button */}
      <div className="flex justify-center mb-3">
        <button
          onClick={onSave}
          className="text-sm text-neutral-500 hover:text-skip transition-colors"
          title="Save to favorites"
        >
          &#9733; Save
        </button>
      </div>

      {/* Volume */}
      <div className="flex items-center gap-3 px-2">
        <span className="text-xs text-neutral-500">&#128264;</span>
        <input
          type="range"
          min={0}
          max={100}
          value={volume}
          onChange={(e) => onVolumeChange(Number(e.target.value))}
          className="flex-1"
        />
        <span className="text-xs text-neutral-500 w-8 text-right">{volume}%</span>
      </div>
    </div>
  );
}
