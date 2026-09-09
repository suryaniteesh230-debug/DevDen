import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Check,
  FileCheck2,
  GitCompareArrows,
  Lightbulb,
  LockKeyhole,
  Route,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

const DEMO_STEPS = [
  {
    id: "signals",
    tab: "Overview",
    target: "demo-assessment",
    icon: GitCompareArrows,
    title: "Four decisions, never one mystery score",
    description:
      "Cardiac model output, provisional triage, clinical reasoning, and queue priority stay visually and semantically independent.",
    proof: "Show how a model probability supports—but never becomes—ESI or queue priority.",
  },
  {
    id: "reassessment",
    tab: "Inputs",
    target: "demo-observations",
    icon: Activity,
    title: "A queue that reacts to deterioration",
    description:
      "Add a second vital set, rerun the same workflow, and watch the existing patient reorder without losing prior snapshots.",
    proof: "Demonstrate repeated-vital comparison and append-only reassessment.",
  },
  {
    id: "explainability",
    tab: "Reasoning",
    target: "demo-explainability",
    icon: Route,
    title: "Every recommendation has a trail",
    description:
      "Tree SHAP, deterministic triage rules, priority rules, retrieved sources, graph evidence, and controlled tool calls remain inspectable.",
    proof: "Open the influence bars, then expand the rule and tool traces.",
  },
  {
    id: "multimodal",
    tab: "Inputs",
    target: "demo-multimodal",
    icon: FileCheck2,
    title: "Multimodal input with provenance",
    description:
      "OCR and speech create source-labelled observations, preserve conflicts, and never silently replace manual clinician entries.",
    proof: "Upload a report or record speech, then show extracted fields and conflict handling.",
  },
  {
    id: "resilience",
    tab: "Overview",
    target: "demo-assessment",
    icon: ShieldCheck,
    title: "Useful even when the cloud fails",
    description:
      "The local cardiac, triage, queue, safety, and explanation path survives a missing or failed reasoning provider.",
    proof: "Point to an unavailable reasoning card while the deterministic results remain visible.",
  },
  {
    id: "privacy",
    tab: "Reasoning",
    target: "demo-reasoning",
    icon: LockKeyhole,
    title: "Privacy designed into the agent boundary",
    description:
      "The cloud reasoning payload omits names, phone numbers, IDs, exact birth dates, and raw notes while local tools bind encounter context.",
    proof: "Use the controlled tool trace to explain the PHI-minimized boundary.",
  },
];

export default function JudgeDemoPanel({ open, onClose, onNavigate }) {
  const [completed, setCompleted] = useState([]);

  useEffect(() => {
    if (!open) return undefined;
    const escape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [open, onClose]);

  if (!open) return null;

  const launch = (step) => {
    setCompleted((items) => (items.includes(step.id) ? items : [...items, step.id]));
    onNavigate(step.tab, step.target);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="Judge demo guide"
    >
      <button
        type="button"
        className="absolute inset-0 bg-foreground/25 backdrop-blur-[2px] view-enter"
        onClick={onClose}
        aria-label="Close judge demo"
      />
      <aside className="relative flex h-full w-full max-w-md flex-col border-l border-border bg-card shadow-2xl view-enter">
        <div className="border-b border-border bg-gradient-to-br from-primary/12 to-transparent p-5">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
              <Sparkles size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-bold tracking-[0.12em] text-primary uppercase">
                Interactive presentation guide
              </p>
              <h2 className="mt-1 text-lg font-bold tracking-tight">
                What makes NextCare different
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Six claims you can prove live—without fabricated metrics or marketing-only slides.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="pressable flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground"
              aria-label="Close guide"
            >
              <X size={14} />
            </button>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-500"
                style={{ width: `${(completed.length / DEMO_STEPS.length) * 100}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-muted-foreground">
              {completed.length}/{DEMO_STEPS.length}
            </span>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <div className="space-y-2">
            {DEMO_STEPS.map((step, index) => {
              const Icon = step.icon;
              const done = completed.includes(step.id);
              return (
                <button
                  type="button"
                  key={step.id}
                  onClick={() => launch(step)}
                  className="interactive-card group w-full rounded-xl border border-border bg-surface/45 p-3.5 text-left queue-enter"
                  style={{ "--item-index": index }}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${done ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary group-hover:bg-primary group-hover:text-primary-foreground"}`}
                    >
                      {done ? <Check size={14} /> : <Icon size={14} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-semibold">{step.title}</span>
                      <span className="mt-1 block text-[11px] leading-relaxed text-muted-foreground">
                        {step.description}
                      </span>
                      <span className="mt-2 flex items-start gap-1.5 rounded-md bg-primary/6 px-2 py-1.5 text-[10px] leading-relaxed text-primary">
                        <Lightbulb size={11} className="mt-0.5 shrink-0" />
                        {step.proof}
                      </span>
                    </span>
                    <ArrowRight
                      size={13}
                      className="mt-1 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-primary"
                    />
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="border-t border-border bg-surface/50 p-4">
          <div className="flex items-start gap-2 text-[10px] leading-relaxed text-muted-foreground">
            <BrainCircuit size={13} className="mt-0.5 shrink-0 text-primary" />
            Lead with the worsening-vitals reassessment. It connects data capture, deterministic
            policy, persistence, explainability, and live queue movement in one story.
          </div>
        </div>
      </aside>
    </div>
  );
}
