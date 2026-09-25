import { useState } from "react";
import { ChevronDown } from "lucide-react";
import Sparkline from "./Sparkline";

export default function VitalCard({ vital }) {
  const [open, setOpen] = useState(false);
  const previous = vital.series.at(-2);
  const delta = previous == null ? null : vital.value - previous;
  return (
    <button
      type="button"
      onClick={() => setOpen((value) => !value)}
      aria-expanded={open}
      className="interactive-card pressable w-full rounded-lg border border-border bg-card px-3.5 py-3 text-left"
    >
      <div className="flex items-baseline justify-between">
        <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          {vital.label}
        </p>
        <span className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
          {vital.source}
          <ChevronDown size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
        </span>
      </div>

      <div className="mt-1.5 flex items-end justify-between gap-2">
        <p className="font-mono text-2xl leading-none text-foreground">
          {vital.display ?? vital.value}
          <span className="ml-1 text-xs text-muted-foreground">{vital.unit}</span>
        </p>
        <Sparkline series={vital.series} tone="muted" />
      </div>

      <p className="mt-2 font-mono text-[10px] text-muted-foreground">
        measured{" "}
        {new Date(vital.measuredAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
      </p>
      <div className="smooth-collapse" data-open={open}>
        <div>
          <div className="mt-2 border-t border-border pt-2 text-[10px] text-muted-foreground">
            <span>{vital.series.length} recorded value(s)</span>
            {delta != null ? (
              <span className="ml-2 font-mono text-foreground">
                latest change {delta > 0 ? "+" : ""}
                {delta.toFixed(1)} {vital.unit}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </button>
  );
}
