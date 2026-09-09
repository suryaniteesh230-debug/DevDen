import { useState } from "react";
import { Activity, Brain, ChevronDown, ListOrdered, LoaderCircle, ShieldAlert } from "lucide-react";
import PriorityBadge from "./PriorityBadge";
import ESIBadge from "./ESIBadge";

export default function AssessmentOverview({
  assessment,
  queueEntry,
  onQueueStatus,
  statusLoading,
}) {
  if (!assessment) return null;
  const cardiac = assessment.cardiac_risk;
  const triage = assessment.triage;
  const priority = assessment.priority;
  const reasoning = assessment.clinical_reasoning;

  return (
    <section className="stagger-grid grid gap-4 xl:grid-cols-2">
      <AssessmentCard icon={Activity} title="Cardiac risk" status={cardiac?.status}>
        {cardiac ? (
          <>
            <p className="text-2xl font-semibold tracking-tight">
              {cardiac.predicted_class === 1 ? "Positive model class" : "Negative model class"}
            </p>
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              probability {(cardiac.probability * 100).toFixed(1)}% · threshold{" "}
              {(cardiac.threshold * 100).toFixed(0)}%
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              {cardiac.model_name} · {cardiac.model_version}
            </p>
          </>
        ) : (
          <Empty text="No persisted cardiac prediction." />
        )}
      </AssessmentCard>

      <AssessmentCard icon={ShieldAlert} title="Emergency triage" status={triage?.status}>
        {triage ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              {triage.prototype_esi_level ? (
                <ESIBadge level={triage.prototype_esi_level} size="lg" />
              ) : (
                <span className="text-sm font-medium">{triage.severity_level}</span>
              )}
              {triage.provisional ? (
                <span className="rounded border border-esi-2/40 bg-esi-2/10 px-2 py-1 text-[10px] font-medium text-esi-2">
                  PROVISIONAL
                </span>
              ) : null}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {triage.policy_name} · {triage.policy_version}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Triggered: {triage.triggered_rule_ids?.join(", ") || "none"}
            </p>
          </>
        ) : (
          <Empty text="No persisted triage assessment." />
        )}
      </AssessmentCard>

      <AssessmentCard
        icon={ListOrdered}
        title="Operational priority"
        status={priority?.queue_status}
      >
        {priority ? (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <PriorityBadge band={priority.priority_band} size="lg" />
              <span className="font-mono text-sm">
                rank {priority.rank ?? "—"} · score {priority.priority_score.toFixed(1)}
              </span>
            </div>
            <p
              className={`mt-2 text-xs ${priority.deterioration_status === "DETECTED" ? "text-esi-1" : "text-muted-foreground"}`}
            >
              Deterioration: {priority.deterioration_status}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {priority.reason_codes.join(" · ")}
            </p>
            {queueEntry ? (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
                {queueEntry.queue_status === "WAITING" ? (
                  <QueueButton disabled={statusLoading} onClick={() => onQueueStatus("CALLED")}>
                    Call patient
                  </QueueButton>
                ) : null}
                {["WAITING", "CALLED"].includes(queueEntry.queue_status) ? (
                  <QueueButton
                    disabled={statusLoading}
                    onClick={() => onQueueStatus("IN_ASSESSMENT")}
                  >
                    Start assessment
                  </QueueButton>
                ) : null}
                {queueEntry.queue_status === "IN_ASSESSMENT" ? (
                  <QueueButton disabled={statusLoading} onClick={() => onQueueStatus("COMPLETED")}>
                    Complete
                  </QueueButton>
                ) : null}
                {!["COMPLETED", "REMOVED"].includes(queueEntry.queue_status) ? (
                  <QueueButton
                    disabled={statusLoading}
                    onClick={() => onQueueStatus("REMOVED")}
                    secondary
                  >
                    Remove
                  </QueueButton>
                ) : null}
              </div>
            ) : null}
          </>
        ) : (
          <Empty text="Priority appears after a usable triage workflow." />
        )}
      </AssessmentCard>

      <AssessmentCard icon={Brain} title="Clinical reasoning" status={reasoning?.status}>
        {reasoning ? (
          <>
            <p className="text-sm font-medium">
              {reasoning.status === "SUCCESS" ? reasoning.summary : "Reasoning unavailable"}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {reasoning.status === "SUCCESS" ? reasoning.uncertainty : reasoning.summary}
            </p>
            <p className="mt-2 font-mono text-[10px] text-muted-foreground">
              {reasoning.provider} · {reasoning.model} · {reasoning.termination_reason}
            </p>
          </>
        ) : (
          <Empty text="No persisted clinical reasoning attempt." />
        )}
      </AssessmentCard>
    </section>
  );
}

function AssessmentCard({ icon: Icon, title, status, children }) {
  const [open, setOpen] = useState(true);
  return (
    <article className="interactive-card rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="pressable flex w-full items-center justify-between gap-2 rounded-t-lg px-4 py-3 text-left hover:bg-surface-raised/45"
      >
        <div className="flex items-center gap-1.5">
          <Icon size={13} className="text-primary" />
          <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            {title}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {status ? (
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
              {status}
            </span>
          ) : null}
          <ChevronDown
            size={14}
            className={`text-muted-foreground transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          />
        </div>
      </button>
      <div className="smooth-collapse" data-open={open}>
        <div>
          <div className="border-t border-border px-4 pt-3 pb-4">{children}</div>
        </div>
      </div>
    </article>
  );
}

function QueueButton({ children, secondary = false, ...props }) {
  return (
    <button
      {...props}
      className={`pressable inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-medium disabled:opacity-50 ${secondary ? "border-border text-muted-foreground hover:text-foreground" : "border-primary/40 bg-primary/10 text-primary hover:bg-primary/15"}`}
    >
      {props.disabled ? <LoaderCircle size={11} className="animate-spin" /> : null}
      {children}
    </button>
  );
}

function Empty({ text }) {
  return <p className="text-xs text-muted-foreground">{text}</p>;
}
