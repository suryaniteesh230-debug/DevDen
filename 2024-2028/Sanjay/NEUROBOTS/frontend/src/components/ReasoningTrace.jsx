import { useState } from "react";
import ReasoningStep from "./ReasoningStep";

export default function ReasoningTrace({ reasoning }) {
  const [open, setOpen] = useState({ 1: true, 2: true, 3: true, 4: true });
  const [copied, setCopied] = useState("");
  const toggle = (step) => setOpen((previous) => ({ ...previous, [step]: !previous[step] }));
  const copyReference = async (value) => {
    await navigator.clipboard?.writeText(value);
    setCopied(value);
    window.setTimeout(() => setCopied(""), 1200);
  };

  if (!reasoning) {
    return <EmptyReasoning message="Run an assessment to create a clinical reasoning record." />;
  }
  if (reasoning.status !== "SUCCESS") {
    return (
      <EmptyReasoning
        message={
          reasoning.summary ||
          "Clinical reasoning is unavailable. Local assessment results remain available."
        }
        detail={`${reasoning.termination_reason || reasoning.status} · ${reasoning.provider || "provider unavailable"}`}
      />
    );
  }

  const differential = reasoning.differential_considerations || [];
  const evidence = reasoning.clinical_evidence || [];
  const graphEvidence = reasoning.knowledge_graph_evidence || [];
  const toolCalls = reasoning.tool_calls || [];

  return (
    <section className="interactive-card rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold">Clinical reasoning workspace</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Evidence-backed differential considerations; not a diagnosis or private chain-of-thought.
        </p>
      </div>

      <ReasoningStep
        index={1}
        title="Clinical summary"
        subtitle={reasoning.model}
        open={open[1]}
        onToggle={() => toggle(1)}
      >
        <p className="text-xs leading-relaxed text-muted-foreground">{reasoning.summary}</p>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">Uncertainty:</span> {reasoning.uncertainty}
        </p>
      </ReasoningStep>

      <ReasoningStep
        index={2}
        title="Differential considerations"
        subtitle={`${differential.length} qualitative items`}
        open={open[2]}
        onToggle={() => toggle(2)}
      >
        <div className="stagger-grid space-y-2.5">
          {differential.map((item) => (
            <div
              key={item.condition}
              className="interactive-card rounded-md border border-border bg-surface-raised/60 p-3"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-medium">{item.condition}</p>
                <span className="font-mono text-[10px] text-primary">
                  {item.support_level} support
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                {item.supporting_findings.join(" · ") || "No supporting findings supplied"}
              </p>
              {item.contradicting_or_missing_findings.length ? (
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  Missing/contradicting: {item.contradicting_or_missing_findings.join(" · ")}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </ReasoningStep>

      <ReasoningStep
        index={3}
        title="Evidence consulted"
        subtitle={`${evidence.length + graphEvidence.length} grounded references`}
        open={open[3]}
        onToggle={() => toggle(3)}
      >
        <div className="stagger-grid grid gap-2 md:grid-cols-2">
          {evidence.map((item) => (
            <button
              type="button"
              onClick={() => copyReference(item.chunk_id)}
              key={item.chunk_id}
              title="Copy evidence reference"
              className="pressable rounded-md border border-border bg-surface-raised/60 p-3 text-left hover:border-primary/30"
            >
              <p className="flex items-center justify-between gap-2 font-mono text-[10px] text-primary">
                {item.source_id}
                <span className="text-[8px] text-muted-foreground">
                  {copied === item.chunk_id ? "copied" : "copy ref"}
                </span>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Corpus chunk {item.chunk_id} · relevance {item.relevance.toFixed(3)}
              </p>
            </button>
          ))}
          {graphEvidence.map((item) => (
            <button
              type="button"
              onClick={() => copyReference(item.edge_id)}
              key={item.edge_id}
              title="Copy graph evidence reference"
              className="pressable rounded-md border border-border bg-surface-raised/60 p-3 text-left hover:border-primary/30"
            >
              <p className="flex items-center justify-between gap-2 font-mono text-[10px] text-primary">
                {item.source_id}
                <span className="text-[8px] text-muted-foreground">
                  {copied === item.edge_id ? "copied" : "copy ref"}
                </span>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.source_concept} → {item.relationship} → {item.target_concept}
              </p>
            </button>
          ))}
          {!evidence.length && !graphEvidence.length ? (
            <p className="text-xs text-muted-foreground">
              No RAG or knowledge-graph evidence was returned.
            </p>
          ) : null}
        </div>
      </ReasoningStep>

      <ReasoningStep
        index={4}
        title="Tool and safety trace"
        subtitle={`${toolCalls.length} local tool calls`}
        open={open[4]}
        onToggle={() => toggle(4)}
      >
        <ol className="stagger-grid space-y-2">
          {toolCalls.map((item) => (
            <li
              key={`${item.step}-${item.tool}`}
              className="interactive-card flex gap-2 rounded-md border border-transparent p-2 text-xs text-muted-foreground hover:border-border hover:bg-surface-raised/50"
            >
              <span className="font-mono text-primary">{item.step}.</span>
              <span>
                <span className="font-medium text-foreground">{item.tool}</span> — {item.purpose} (
                {item.status})
              </span>
            </li>
          ))}
        </ol>
        {reasoning.important_missing_information?.length ? (
          <p className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
            Important missing information: {reasoning.important_missing_information.join(" · ")}
          </p>
        ) : null}
        {reasoning.limitations?.length ? (
          <p className="mt-2 text-xs text-muted-foreground">
            Limitations: {reasoning.limitations.join(" · ")}
          </p>
        ) : null}
      </ReasoningStep>
    </section>
  );
}

function EmptyReasoning({ message, detail }) {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-semibold">Clinical reasoning</h3>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{message}</p>
      {detail ? <p className="mt-2 font-mono text-[10px] text-muted-foreground">{detail}</p> : null}
    </section>
  );
}
