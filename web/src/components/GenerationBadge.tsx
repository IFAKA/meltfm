/**
 * Queue visualization — shows what's coming up next.
 * When params are known: shows track tags.
 * When generating without params: shows spinner (queue was cleared/reset).
 */

type Props = {
  generating: boolean;
  elapsed: number;
  params: Record<string, unknown> | null;
};

export default function GenerationBadge({ generating, elapsed, params }: Props) {
  if (!generating) return null;

  const tags = typeof params?.tags === "string" ? params.tags : null;
  const bpm = typeof params?.bpm === "number" ? params.bpm : null;

  return (
    <div className="mx-6 mb-3 rounded-lg border border-neutral-800 bg-neutral-900/60 overflow-hidden">
      {/* Header row */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-800/60">
        <span className="text-[10px] font-medium uppercase tracking-widest text-neutral-500">Up Next</span>
        <div className="ml-auto flex items-center gap-1.5 text-neutral-600 text-xs">
          <span className="animate-spin inline-block text-radio-accent/60 text-[10px]">&#9684;</span>
          <span>{Math.round(elapsed)}s</span>
        </div>
      </div>

      {/* Content */}
      <div className="px-3 py-2">
        {tags ? (
          <>
            <div className="text-sm text-neutral-300 leading-snug truncate">{tags}</div>
            {bpm && (
              <div className="text-xs text-neutral-600 mt-0.5">{bpm} BPM</div>
            )}
          </>
        ) : (
          <div className="text-sm text-neutral-600 italic">building next track...</div>
        )}
      </div>
    </div>
  );
}
