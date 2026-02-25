/**
 * Pipeline event log — real-time stream of engine events for debugging.
 * Newest events shown first. Collapsible.
 */
import { useState } from "react";
import type { EventEntry } from "@/hooks/useRadio";

const EVENT_ICON: Record<string, string> = {
  thinking: "◎",
  generation_start: "⚡",
  generation_done: "✓",
  now_playing: "▶",
  regenerating: "↺",
  reaction_feedback: "✦",
  error: "✕",
  radio_switched: "⤁",
  disk_full: "⚠",
};

const LEVEL_CLS: Record<EventEntry["level"], string> = {
  info: "text-neutral-400",
  warn: "text-yellow-500/90",
  error: "text-dislike",
};

function fmtTime(ts: number): string {
  const d = new Date(ts);
  const hh = d.getHours().toString().padStart(2, "0");
  const mm = d.getMinutes().toString().padStart(2, "0");
  const ss = d.getSeconds().toString().padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

type Props = {
  events: EventEntry[];
  defaultCollapsed?: boolean;
};

export default function EventLog({ events, defaultCollapsed = false }: Props) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  const hasError = events.some((e) => e.level === "error");
  const hasWarn = !hasError && events.some((e) => e.level === "warn");

  return (
    <div className="border-t border-neutral-800">
      {/* Collapsible header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-neutral-900/40 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium uppercase tracking-widest text-neutral-500">
            Pipeline Log
          </span>
          {events.length > 0 && (
            <span className="text-[10px] text-neutral-700">{events.length}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasError && <span className="w-1.5 h-1.5 rounded-full bg-dislike" title="Error" />}
          {hasWarn && <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" title="Warning" />}
          <span className="text-neutral-700 text-[10px]">{collapsed ? "▾" : "▴"}</span>
        </div>
      </button>

      {!collapsed && (
        <div className="overflow-y-auto max-h-56 px-3 pb-3">
          {events.length === 0 ? (
            <p className="text-[11px] text-neutral-700 italic py-2 px-1">
              Waiting for events…
            </p>
          ) : (
            <div className="space-y-0.5">
              {events.map((e) => (
                <div key={e.id} className="flex items-start gap-1.5 py-[3px]">
                  {/* Timestamp */}
                  <span className="text-[10px] text-neutral-700 font-mono shrink-0 mt-px leading-tight">
                    {fmtTime(e.ts)}
                  </span>
                  {/* Icon */}
                  <span className={`text-[10px] shrink-0 mt-px ${LEVEL_CLS[e.level]}`}>
                    {EVENT_ICON[e.type] ?? "·"}
                  </span>
                  {/* Message */}
                  <span className={`text-[11px] leading-snug ${LEVEL_CLS[e.level]}`}>
                    {e.summary}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
