/**
 * Generation pipeline visualization.
 * Shows LLM → ACE-Step step indicators with live status.
 */
import type { PipelineState } from "@/hooks/useRadio";

type StepStatus = "idle" | "active" | "done" | "error";

function StepDot({ status }: { status: StepStatus }) {
  const cls = {
    idle: "bg-neutral-700",
    active: "bg-radio-accent animate-pulse",
    done: "bg-like",
    error: "bg-dislike",
  }[status];
  return <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${cls}`} />;
}

type Props = {
  generating: boolean;
  elapsed: number;
  params: Record<string, unknown> | null;
  pipeline: PipelineState;
};

export default function GenerationBadge({ generating, elapsed, params, pipeline }: Props) {
  if (!generating) return null;

  const tags = typeof params?.tags === "string" ? params.tags : null;
  const bpm = typeof params?.bpm === "number" ? params.bpm : null;

  // Derive step statuses from pipeline state
  const llmStatus: StepStatus =
    pipeline.stage === "error" && !pipeline.llmDone ? "error" :
    pipeline.llmDone ? "done" :
    pipeline.stage === "thinking" ? "active" : "idle";

  const aceStatus: StepStatus =
    pipeline.stage === "error" && pipeline.llmDone ? "error" :
    pipeline.stage === "idle" && pipeline.llmDone ? "done" :
    pipeline.stage === "generating" ? "active" : "idle";

  const llmColor = { idle: "text-neutral-600", active: "text-radio-accent", done: "text-neutral-400", error: "text-dislike" }[llmStatus];
  const aceColor = { idle: "text-neutral-600", active: "text-radio-accent", done: "text-neutral-400", error: "text-dislike" }[aceStatus];

  return (
    <div className="mx-6 mb-3 rounded-lg border border-neutral-800 bg-neutral-900/60 overflow-hidden">
      {/* Header: "Up Next" label + pipeline step indicators */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-neutral-800/60">
        <span className="text-[10px] font-medium uppercase tracking-widest text-neutral-500">
          Up Next
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <StepDot status={llmStatus} />
          <span className={`text-[11px] font-medium ${llmColor}`}>LLM</span>
          <span className="text-neutral-700 text-xs mx-0.5">→</span>
          <StepDot status={aceStatus} />
          <span className={`text-[11px] font-medium ${aceColor}`}>
            ACE-Step
            {aceStatus === "active" && elapsed > 0 && (
              <span className="text-neutral-600 font-normal ml-1">{Math.round(elapsed)}s</span>
            )}
          </span>
        </div>
      </div>

      {/* Content: track preview or status */}
      <div className="px-3 py-2">
        {tags ? (
          <>
            <div className="text-sm text-neutral-300 leading-snug truncate">{tags}</div>
            {bpm && (
              <div className="text-xs text-neutral-600 mt-0.5">{bpm} BPM</div>
            )}
          </>
        ) : (
          <div className="text-sm text-neutral-600 italic">
            {pipeline.stage === "thinking" ? "LLM thinking…" : "building next track…"}
          </div>
        )}

        {/* LLM warnings */}
        {pipeline.warnings.length > 0 && (
          <div className="mt-1.5 text-[11px] text-yellow-600/80 flex items-start gap-1">
            <span>⚠</span>
            <span>
              {pipeline.warnings[0]}
              {pipeline.warnings.length > 1 && (
                <span className="text-neutral-600"> +{pipeline.warnings.length - 1} more</span>
              )}
            </span>
          </div>
        )}

        {/* Generation error */}
        {pipeline.stage === "error" && pipeline.lastError && (
          <div className="mt-1.5 text-[11px] text-dislike/80 flex items-start gap-1">
            <span>✕</span>
            <span className="line-clamp-2">{pipeline.lastError}</span>
          </div>
        )}
      </div>
    </div>
  );
}
