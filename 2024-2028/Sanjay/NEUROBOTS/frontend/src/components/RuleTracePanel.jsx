import { useState } from "react";
import { ChevronDown } from "lucide-react";

export default function RuleTracePanel({ triage, priority }) {
  const triageRules = triage?.rule_hits || [];
  const priorityRules = priority?.rule_trace || [];
  if (!triageRules.length && !priorityRules.length) return null;
  return (
    <section className="interactive-card rounded-lg border border-border bg-card p-4">
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        Deterministic rule traces
      </h3>
      <div className="mt-3 space-y-3">
        <Trace title="Emergency triage" items={triageRules} idKey="rule_id" />
        <Trace title="Operational priority" items={priorityRules} idKey="rule_id" />
      </div>
    </section>
  );
}

function Trace({ title, items, idKey }) {
  const [selected, setSelected] = useState(null);
  return (
    <div>
      <p className="text-[11px] font-medium">{title}</p>
      <ul className="mt-1.5 space-y-1.5">
        {items.map((item, index) => {
          const open = selected === index;
          return (
            <li
              key={item[idKey] || index}
              className="overflow-hidden rounded-md border border-border bg-surface-raised/50"
            >
              <button
                type="button"
                onClick={() => setSelected(open ? null : index)}
                className="pressable flex w-full items-start gap-2 p-2 text-left text-[11px] text-muted-foreground hover:bg-surface-raised"
              >
                <span
                  className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${item.triggered ? "bg-esi-2 live-dot" : "bg-muted-foreground/35"}`}
                />
                <span className="min-w-0 flex-1">
                  <span className="font-mono text-primary">
                    {item[idKey] || `rule-${index + 1}`}
                  </span>{" "}
                  ·{" "}
                  {item.description ||
                    item.reason ||
                    item.outcome ||
                    (item.triggered ? "triggered" : "not triggered")}
                </span>
                <ChevronDown
                  size={12}
                  className={`mt-0.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
                />
              </button>
              <div className="smooth-collapse" data-open={open}>
                <div>
                  <pre className="overflow-x-auto border-t border-border bg-card/60 p-2 font-mono text-[8px] leading-relaxed text-muted-foreground">
                    {JSON.stringify(item, null, 2)}
                  </pre>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
