/**
 * Subtle indicator showing next track is being generated.
 */
import { Badge } from "@/components/ui/badge";

type Props = {
  generating: boolean;
  elapsed: number;
  params: Record<string, unknown> | null;
};

export default function GenerationBadge({ generating, elapsed, params }: Props) {
  if (!generating) return null;

  const tags = typeof params?.tags === "string" ? params.tags : "";
  const label = tags ? `Next: ${tags}` : "Building next track...";

  return (
    <div className="px-6 py-2 flex items-center gap-2 text-sm text-neutral-400">
      <span className="animate-spin text-radio-accent inline-block">&#9684;</span>
      <span className="truncate">{label}</span>
      <Badge variant="outline" className="ml-auto shrink-0 border-neutral-700 text-neutral-500 font-normal">
        {Math.round(elapsed)}s
      </Badge>
    </div>
  );
}
