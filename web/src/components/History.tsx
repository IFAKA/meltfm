/**
 * Recent tracks + Saved favorites, with replay on click.
 */
import { useEffect, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Play } from "lucide-react";

type TrackItem = {
  id?: string;
  filename: string;
  tags: string;
  bpm?: number;
  key_scale?: string;
  reaction?: string;
};

type Props = {
  radioName: string;
  nowPlayingId?: string | null;
  onPlayUrl: (url: string) => void;
};

type Tab = "recent" | "saved";

export default function History({ radioName, nowPlayingId, onPlayUrl }: Props) {
  const [tab, setTab] = useState<Tab>("recent");
  const [recent, setRecent] = useState<TrackItem[]>([]);
  const [saved, setSaved] = useState<TrackItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/radios/${encodeURIComponent(radioName)}/history?limit=20`)
      .then((r) => r.json())
      .then((data: { history?: TrackItem[] }) => {
        setRecent(data.history || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [radioName, nowPlayingId]);

  useEffect(() => {
    fetch(`/api/radios/${encodeURIComponent(radioName)}/favorites`)
      .then((r) => r.json())
      .then((data: { favorites?: TrackItem[] }) => setSaved(data.favorites || []))
      .catch(() => {});
  }, [radioName]);

  const reactionIcon = (r?: string) => {
    if (r === "liked") return <span className="text-like">&#9829;</span>;
    if (r === "disliked") return <span className="text-dislike">&#10007;</span>;
    if (r === "skipped") return <span className="text-skip">&raquo;</span>;
    return <span className="text-neutral-600">&middot;</span>;
  };

  const audioUrl = (item: TrackItem) => {
    return `/audio/${encodeURIComponent(radioName)}/${encodeURIComponent(item.filename)}`;
  };

  const items = tab === "recent" ? recent : saved;

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      <div className="flex gap-4 px-6 pt-3 pb-2 shrink-0 border-b border-neutral-800">
        <button
          onClick={() => setTab("recent")}
          className={`text-xs uppercase tracking-wider pb-1 border-b-2 transition-colors ${
            tab === "recent"
              ? "border-radio-accent text-radio-accent"
              : "border-transparent text-neutral-500 hover:text-neutral-300"
          }`}
        >
          Recent
        </button>
        <button
          onClick={() => setTab("saved")}
          className={`text-xs uppercase tracking-wider pb-1 border-b-2 transition-colors ${
            tab === "saved"
              ? "border-radio-accent text-radio-accent"
              : "border-transparent text-neutral-500 hover:text-neutral-300"
          }`}
        >
          Saved {saved.length > 0 && <span className="ml-1 text-neutral-600">({saved.length})</span>}
        </button>
      </div>

      {/* List */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="px-6 py-2">
          {loading && tab === "recent" ? (
            <div className="text-sm text-neutral-500 py-2">Loading...</div>
          ) : items.length === 0 ? (
            <div className="text-sm text-neutral-500 py-2">
              {tab === "saved" ? "No saved tracks yet — bookmark one!" : "No tracks yet"}
            </div>
          ) : (
            <div className="space-y-0.5">
              {items.map((item, i) => (
                <button
                  key={item.filename || i}
                  onClick={() => onPlayUrl(audioUrl(item))}
                  className="group w-full flex items-center gap-2 py-1.5 px-2 -mx-2 rounded text-sm hover:bg-neutral-800 transition-colors text-left"
                >
                  <span className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-radio-accent">
                    <Play className="size-3.5" />
                  </span>
                  <span className="truncate flex-1 text-neutral-300 group-hover:text-white transition-colors">
                    {item.tags}
                  </span>
                  <span className="shrink-0">{reactionIcon(item.reaction)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
