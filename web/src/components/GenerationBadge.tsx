/**
 * Subtle indicator showing next track is being generated.
 */

type Props = {
  generating: boolean;
  elapsed: number;
  params: Record<string, any> | null;
};

export default function GenerationBadge({ generating, elapsed, params }: Props) {
  if (!generating) return null;

  const tags = params?.tags || "";
  const label = tags ? `Next: ${tags}` : "Building next track...";

  return (
    <div className="px-6 py-2 flex items-center gap-2 text-sm text-neutral-400">
      <span className="animate-spin text-accent">&#9684;</span>
      <span className="truncate">{label}</span>
      <span className="text-neutral-600 ml-auto shrink-0">{Math.round(elapsed)}s</span>
    </div>
  );
}
