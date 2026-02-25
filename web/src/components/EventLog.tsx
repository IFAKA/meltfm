/**
 * Pipeline event log — real-time stream of engine events for debugging.
 * Newest events shown first. Collapsible. Each entry is clickable to expand payload.
 */
import { useState } from "react";
import type { EventEntry } from "@/hooks/useRadio";

const EVENT_ICON: Record<string, string> = {
  thinking: "◎",
  generation_start: "⚡",
  generation_done: "✓",
  generation_progress: "⋯",
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

function fmtDelta(ms: number): string {
  if (ms < 1000) return `+${ms}ms`;
  return `+${(ms / 1000).toFixed(1)}s`;
}

type Props = {
  events: EventEntry[];
  defaultCollapsed?: boolean;
};

function EventRow({ e }: { e: EventEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasPayload = e.payload && Object.keys(e.payload).length > 0;

  return (
    <div className="border-b border-neutral-900/50 last:border-0">
      <button
        onClick={() => hasPayload && setExpanded((x) => !x)}
        className={`w-full flex items-start gap-1.5 py-[3px] text-left ${hasPayload ? "hover:bg-neutral-900/30 cursor-pointer" : "cursor-default"}`}
      >
        {/* Timestamp + delta */}
        <span className="text-[10px] text-neutral-700 font-mono shrink-0 mt-px leading-tight">
          {fmtTime(e.ts)}
          {e.deltaMs != null && (
            <span className="text-neutral-800 ml-1">{fmtDelta(e.deltaMs)}</span>
          )}
        </span>
        {/* Icon */}
        <span className={`text-[10px] shrink-0 mt-px ${LEVEL_CLS[e.level]}`}>
          {EVENT_ICON[e.type] ?? "·"}
        </span>
        {/* Message */}
        <span className={`text-[11px] leading-snug flex-1 ${LEVEL_CLS[e.level]}`}>
          {e.summary}
        </span>
        {/* Expand toggle */}
        {hasPayload && (
          <span className="text-[9px] text-neutral-700 shrink-0 mt-px">
            {expanded ? "▾" : "▸"}
          </span>
        )}
      </button>

      {expanded && hasPayload && (
        <div className="mx-1 mb-1.5 border border-neutral-800 rounded bg-neutral-950/60 px-2 py-1.5">
          <pre className="text-[10px] font-mono text-neutral-500 whitespace-pre-wrap break-all leading-relaxed">
            {JSON.stringify(e.payload, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

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
            <div>
              {events.map((e) => (
                <EventRow key={e.id} e={e} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
