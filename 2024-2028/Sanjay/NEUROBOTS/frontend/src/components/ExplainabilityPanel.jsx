import { useState } from "react";
import { ChevronDown } from "lucide-react";

export default function ExplainabilityPanel({ features }) {
  const [open, setOpen] = useState(true);
  const [selected, setSelected] = useState(null);
  if (!features || features.length === 0) return null;

  const max = Math.max(...features.map((f) => f.magnitude), 0.000001);

  return (
    <section className="interactive-card rounded-lg border border-border bg-card">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="pressable flex w-full items-center justify-between px-4 py-3 text-left hover:bg-surface-raised/40"
      >
        <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Feature influence
        </span>
        <ChevronDown
          size={15}
          className={`text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      <div className="smooth-collapse" data-open={open}>
        <div>
          <div className="space-y-2.5 border-t border-border px-4 py-3.5">
            {features.map((feature, index) => (
              <button
                type="button"
                onClick={() => setSelected(selected === index ? null : index)}
                key={`${feature.feature}-${index}`}
                className={`pressable flex w-full items-center gap-3 rounded-md p-1.5 text-left ${selected === index ? "bg-primary/8" : "hover:bg-surface-raised/60"}`}
              >
                <p className="w-44 shrink-0 truncate text-xs text-muted-foreground">
                  {feature.feature} · {feature.observed_value}
                </p>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`animated-bar h-full rounded-full ${feature.shap_value >= 0 ? "bg-esi-2/80" : "bg-primary/75"}`}
                    style={{
                      width: `${(feature.magnitude / max) * 100}%`,
                      animationDelay: `${index * 70}ms`,
                    }}
                  />
                </div>
                <span
                  className={`w-12 shrink-0 text-right font-mono text-[11px] ${feature.shap_value >= 0 ? "text-esi-2" : "text-primary"}`}
                >
                  {feature.shap_value >= 0 ? "+" : ""}
                  {feature.shap_value.toFixed(3)}
                </span>
              </button>
            ))}
            {selected != null ? (
              <div className="view-enter rounded-md border border-primary/20 bg-primary/6 p-2.5 text-[10px] leading-relaxed text-muted-foreground">
                <span className="font-medium text-foreground">{features[selected].feature}</span> at
                observed value{" "}
                <span className="font-mono text-foreground">
                  {features[selected].observed_value}
                </span>{" "}
                pushed this model output{" "}
                <span
                  className={features[selected].shap_value >= 0 ? "text-esi-2" : "text-primary"}
                >
                  {features[selected].shap_value >= 0 ? "toward" : "away from"} the positive class
                </span>
                . This describes model behavior, not clinical causation.
              </div>
            ) : null}
            <p className="pt-1 font-mono text-[10px] text-muted-foreground/70">
              Tree SHAP model contributions · not clinical causation
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
