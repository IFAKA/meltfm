/**
 * Recent tracks list with reaction indicators.
 */
import { useEffect, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

type HistoryItem = {
  id: string;
  tags: string;
  bpm: number;
  key_scale: string;
  reaction: string;
};

type Props = {
  radioName: string;
};

export default function History({ radioName }: Props) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/radios/${encodeURIComponent(radioName)}/history?limit=20`)
      .then((r) => r.json())
      .then((data: { history?: HistoryItem[] }) => {
        setItems(data.history || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [radioName]);

  const reactionIcon = (r: string) => {
    if (r === "liked") return <span className="text-like">&#9829;</span>;
    if (r === "disliked") return <span className="text-dislike">&#10007;</span>;
    if (r === "skipped") return <span className="text-skip">&raquo;</span>;
    return <span className="text-neutral-600">&middot;</span>;
  };

  return (
    <ScrollArea className="h-full">
      <div className="px-6 py-3">
        <div className="text-xs text-neutral-500 uppercase tracking-wider mb-2">Recent</div>
        {loading ? (
          <div className="text-sm text-neutral-500">Loading...</div>
        ) : items.length === 0 ? (
          <div className="text-sm text-neutral-500">No tracks yet</div>
        ) : (
          <div className="space-y-1">
            {items.map((item) => (
              <div
                key={item.id}
                className="flex items-center gap-2 py-1.5 text-sm"
              >
                <span className="text-neutral-600 w-8 shrink-0">#{item.id}</span>
                <span className="truncate flex-1 text-neutral-300">{item.tags}</span>
                <span className="shrink-0">{reactionIcon(item.reaction)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
