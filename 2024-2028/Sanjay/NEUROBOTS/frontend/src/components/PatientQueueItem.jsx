import { Clock3 } from "lucide-react";
import PriorityBadge, { priorityStyle } from "./PriorityBadge";

export default function PatientQueueItem({ patient, pending = false, selected, onSelect, index = 0 }) {
  if (pending) {
    return (
      <button
        onClick={() => onSelect(patient.id)}
        aria-current={selected ? "true" : undefined}
        style={{ "--item-index": index }}
        className={`queue-enter group relative w-full border-b border-border px-4 py-3 text-left transition-all duration-200 active:scale-[0.985] ${
          selected ? "bg-surface-raised" : "hover:bg-surface-raised/60"
        }`}
      >
        <span className="absolute inset-y-0 left-0 w-[3px] bg-muted-foreground/40" />
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium group-hover:text-primary">
              {patient.patient_display.display_name}
            </p>
            <p className="font-mono text-[11px] text-muted-foreground">
              age {patient.patient_display.age_years} · {Math.round(patient.waiting_duration_minutes)}m
            </p>
          </div>
          <span className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            <Clock3 size={10} />
            {patient.intake_stage === "REGISTRATION" ? "Needs encounter" : "Needs assessment"}
          </span>
        </div>
        <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">
          {patient.patient_display.chief_complaint}
        </p>
      </button>
    );
  }
  const style = priorityStyle(patient.priority_band);

  return (
    <button
      onClick={() => onSelect(patient.id)}
      aria-current={selected ? "true" : undefined}
      style={{ "--item-index": index }}
      className={`queue-enter group relative w-full border-b border-border px-4 py-3 text-left transition-all duration-200 active:scale-[0.985] ${
        selected
          ? "selected-scan bg-surface-raised shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--color-primary)_18%,transparent)]"
          : "hover:bg-surface-raised/60"
      }`}
    >
      <span className={`absolute inset-y-0 left-0 w-[3px] ${style.dot}`} aria-hidden="true" />

      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium transition-colors group-hover:text-primary">
            {patient.patient_display.display_name}
          </p>
          <p className="font-mono text-[11px] text-muted-foreground">
            age {patient.patient_display.age_years} · rank {patient.rank ?? "—"} ·{" "}
            {Math.round(patient.waiting_duration_minutes)}m
          </p>
        </div>
        <span className="transition-transform duration-200 group-hover:scale-105">
          <PriorityBadge band={patient.priority_band} />
        </span>
      </div>

      <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">
        {patient.patient_display.chief_complaint}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
        <span>severity {patient.triage_severity}</span>
        <span>· score {patient.priority_score.toFixed(1)}</span>
        {patient.deterioration_status === "DETECTED" ? (
          <span className="text-esi-1">· deterioration detected</span>
        ) : null}
      </div>
    </button>
  );
}
