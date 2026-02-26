/**
 * DevPanel — real-time developer visibility panel.
 * Shows: live pipeline state, generation params, timing metrics.
 */
import { useState } from "react";
import type { PipelineState, PipelineStage } from "@/hooks/useRadio";

const STAGE_LABEL: Record<PipelineStage, string> = {
  idle: "Idle",
  waiting: "Waiting",
  thinking: "Thinking",
  generating: "Generating",
  ready: "Ready",
  error: "Error",
};

const STAGE_CLS: Record<PipelineStage, string> = {
  idle: "bg-neutral-800 text-neutral-400",
  waiting: "bg-yellow-950 text-yellow-400",
  thinking: "bg-cyan-950 text-cyan-400",
  generating: "bg-cyan-950 text-cyan-400",
  ready: "bg-green-950 text-green-400",
  error: "bg-red-950 text-red-400",
};

function fmtMs(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

type Props = {
  pipeline: PipelineState;
  generationParams: Record<string, unknown> | null;
  connected: boolean;
  generating: boolean;
  queueReady: boolean;
  llmDurationMs: number | null;
  aceDurationMs: number | null;
  generationElapsed: number;
  defaultCollapsed?: boolean;
};

export default function DevPanel({
  pipeline,
  generationParams,
  connected,
  generating,
  queueReady,
  llmDurationMs,
  aceDurationMs,
  generationElapsed,
  defaultCollapsed = false,
}: Props) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className="border-t border-neutral-800">
      {/* Collapsible header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-neutral-900/40 transition-colors"
      >
        <span className="text-[10px] font-medium uppercase tracking-widest text-neutral-500">
          Dev Panel
        </span>
        <span className="text-neutral-700 text-[10px]">{collapsed ? "▾" : "▴"}</span>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-3">
          {/* Section A — Live State */}
          <div>
            <p className="text-[9px] uppercase tracking-widest text-neutral-600 mb-1.5">Live State</p>
            <div className="flex flex-wrap gap-1.5 items-center">
              {/* Pipeline stage pill */}
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${STAGE_CLS[pipeline.stage]}`}>
                {STAGE_LABEL[pipeline.stage]}
              </span>
              {/* generating badge */}
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${generating ? "bg-cyan-950 text-cyan-400" : "bg-neutral-800 text-neutral-600"}`}>
                gen:{generating ? "true" : "false"}
              </span>
              {/* queueReady badge */}
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${queueReady ? "bg-green-950 text-green-400" : "bg-neutral-800 text-neutral-600"}`}>
                queued:{queueReady ? "true" : "false"}
              </span>
              {/* WS status */}
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full flex items-center gap-1 ${connected ? "bg-green-950 text-green-400" : "bg-neutral-800 text-neutral-500"}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-400" : "bg-neutral-500 animate-pulse"}`} />
                {connected ? "Connected" : "Reconnecting"}
              </span>
            </div>
            {pipeline.warnings.length > 0 && (
              <div className="mt-1.5 text-[10px] text-yellow-500/80 font-mono">
                ⚠ {pipeline.warnings.join("; ")}
              </div>
            )}
          </div>

          {/* Section B — Generation Params */}
          <div>
            <p className="text-[9px] uppercase tracking-widest text-neutral-600 mb-1.5">Generation Params</p>
            {generationParams == null ? (
              <p className="text-[10px] text-neutral-700 italic">No params yet</p>
            ) : (
              <div className="border border-neutral-800 rounded bg-neutral-950/60 px-2 py-1.5 space-y-0.5">
                {Object.entries(generationParams).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-[10px] font-mono">
                    <span className="text-neutral-600 shrink-0 w-24">{k}</span>
                    <span className="text-neutral-400 break-all">
                      {typeof v === "string" ? v : JSON.stringify(v)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section C — Timings */}
          <div>
            <p className="text-[9px] uppercase tracking-widest text-neutral-600 mb-1.5">Timings</p>
            <div className="space-y-0.5">
              <div className="flex gap-2 text-[10px] font-mono">
                <span className="text-neutral-600 shrink-0 w-28">LLM last</span>
                <span className="text-neutral-400">{fmtMs(llmDurationMs)}</span>
              </div>
              <div className="flex gap-2 text-[10px] font-mono">
                <span className="text-neutral-600 shrink-0 w-28">ACE-Step last</span>
                <span className="text-neutral-400">{fmtMs(aceDurationMs)}</span>
              </div>
              <div className="flex gap-2 text-[10px] font-mono">
                <span className="text-neutral-600 shrink-0 w-28">ACE-Step now</span>
                <span className={`${generating ? "text-cyan-400" : "text-neutral-600"}`}>
                  {generating && generationElapsed > 0 ? `${generationElapsed.toFixed(1)}s` : "—"}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
