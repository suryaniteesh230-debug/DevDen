import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import TopBar from "./TopBar";
import PatientQueue from "./PatientQueue";
import VitalsStrip from "./VitalsStrip";
import ClinicalSummaryCard from "./ClinicalSummaryCard";
import AssessmentOverview from "./AssessmentOverview";
import ExplainabilityPanel from "./ExplainabilityPanel";
import ReasoningTrace from "./ReasoningTrace";
import RuleTracePanel from "./RuleTracePanel";
import ClinicalIntakePanel from "./ClinicalIntakePanel";
import JudgeDemoPanel from "./JudgeDemoPanel";
import EcgOverlay from "./EcgOverlay";
import { api, errorMessage } from "@/lib/api";

const TABS = ["Overview", "Reasoning", "Inputs"];

export default function TriageDashboard({ staffUser, onLogout }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("Overview");
  const [selectedQueueId, setSelectedQueueId] = useState("");
  const [activeEncounterId, setActiveEncounterId] = useState("");
  const [activePatientId, setActivePatientId] = useState("");
  const [queueOpen, setQueueOpen] = useState(false);
  const [judgeOpen, setJudgeOpen] = useState(false);

  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    retry: false,
    refetchInterval: 10000,
  });
  const queue = useQuery({
    queryKey: ["queue"],
    queryFn: api.listQueue,
    retry: 1,
    refetchInterval: 5000,
  });
  const pendingQueue = useQuery({
    queryKey: ["queue", "pending"],
    queryFn: api.listPendingQueue,
    retry: 1,
    refetchInterval: 5000,
  });
  const patients = queue.data || [];
  const pendingPatients = pendingQueue.data || [];
  const selectedQueue = patients.find((item) => item.id === selectedQueueId) || null;
  const selectedPending =
    pendingPatients.find((item) => item.id === selectedQueueId) || null;

  useEffect(() => {
    if (selectedPending) return;
    if (!patients.length) return;
    const next = selectedQueue || patients[0];
    if (!selectedQueueId) setSelectedQueueId(next.id);
    if (!activeEncounterId) {
      setActiveEncounterId(next.encounter_id);
      setActivePatientId(next.patient_id);
    }
  }, [patients, selectedQueue, selectedPending, selectedQueueId, activeEncounterId]);

  const assessment = useQuery({
    queryKey: ["assessment", activeEncounterId],
    queryFn: () => api.getAssessment(activeEncounterId),
    enabled: Boolean(activeEncounterId),
    retry: false,
  });

  const statusMutation = useMutation({
    mutationFn: ({ queueId, status }) => api.updateQueueStatus(queueId, status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["queue"] });
      await queryClient.invalidateQueries({ queryKey: ["assessment", activeEncounterId] });
    },
  });

  const selectQueue = (queueId) => {
    const item = patients.find((entry) => entry.id === queueId);
    setSelectedQueueId(queueId);
    if (item) {
      setActiveEncounterId(item.encounter_id);
      setActivePatientId(item.patient_id);
      setTab("Overview");
    }
  };

  const selectPending = (pendingId) => {
    const item = pendingPatients.find((entry) => entry.id === pendingId);
    if (!item) return;
    setSelectedQueueId(pendingId);
    setActiveEncounterId(item.encounter_id || "");
    setActivePatientId(item.patient_id);
    setTab("Inputs");
  };

  const selectEncounter = (encounterId, patientId) => {
    setActiveEncounterId(encounterId);
    setActivePatientId(patientId);
    const item = patients.find((entry) => entry.encounter_id === encounterId);
    const pendingItem = pendingPatients.find((entry) => entry.encounter_id === encounterId);
    setSelectedQueueId(item?.id || pendingItem?.id || "");
    setTab("Inputs");
  };

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["queue"] }),
      queryClient.invalidateQueries({ queryKey: ["assessment", activeEncounterId] }),
    ]);
  };

  const showDemoTarget = (nextTab, targetId) => {
    setTab(nextTab);
    setJudgeOpen(false);
    window.setTimeout(() => {
      const target = document.getElementById(targetId);
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("demo-spotlight");
      window.setTimeout(() => target.classList.remove("demo-spotlight"), 1900);
    }, 120);
  };

  const current = assessment.data;
  const vitals = useMemo(() => mapVitals(current?.encounter?.vital_signs || []), [current]);
  const queueForEncounter =
    patients.find((entry) => entry.encounter_id === activeEncounterId) ||
    selectedQueue ||
    current?.priority;

  return (
    <div className="clinical-ambient flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <EcgOverlay />
      <TopBar
        waitingCount={patients.length + pendingPatients.length}
        backendOnline={health.isSuccess}
        refreshing={queue.isFetching || pendingQueue.isFetching || assessment.isFetching}
        onRefresh={refresh}
        onOpenQueue={() => setQueueOpen(true)}
        onOpenJudgeMode={() => setJudgeOpen(true)}
        staffUser={staffUser}
        onLogout={onLogout}
      />
      <div className="flex min-h-0 flex-1">
        {queueOpen ? (
          <button
            type="button"
            aria-label="Close patient queue"
            onClick={() => setQueueOpen(false)}
            className="fixed inset-0 z-40 bg-foreground/25 backdrop-blur-[2px] lg:hidden"
          />
        ) : null}
        <aside
          className={`fixed inset-y-0 left-0 z-50 flex w-80 shrink-0 flex-col border-r border-border bg-surface shadow-2xl transition-transform duration-300 lg:static lg:z-auto lg:translate-x-0 lg:shadow-none ${queueOpen ? "translate-x-0" : "-translate-x-full"}`}
        >
          <PatientQueue
            patients={patients}
            pendingPatients={pendingPatients}
            selectedId={selectedQueueId}
            onSelect={selectQueue}
            onSelectPending={selectPending}
            loading={queue.isLoading || pendingQueue.isLoading}
            error={
              queue.error
                ? errorMessage(queue.error)
                : pendingQueue.error
                  ? errorMessage(pendingQueue.error)
                  : ""
            }
            onClose={() => setQueueOpen(false)}
          />
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="flex items-center gap-1 border-b border-border bg-surface px-5 py-2">
            {TABS.map((item) => (
              <button
                key={item}
                onClick={() => setTab(item)}
                aria-selected={tab === item}
                role="tab"
                className={`pressable rounded-md px-3 py-1.5 text-xs font-medium ${tab === item ? "bg-foreground text-background shadow-sm" : "text-muted-foreground hover:bg-surface-raised hover:text-foreground"}`}
              >
                {item}
              </button>
            ))}
            <p className="ml-auto hidden text-[10px] text-muted-foreground md:block">
              Clinical decision-support prototype · clinician review required
            </p>
          </div>
          <div key={tab} className="view-enter space-y-4 p-4 md:p-5">
            {current ? (
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h1 className="text-lg font-semibold tracking-tight">
                  {current.patient.first_name} {current.patient.last_name}
                </h1>
                <p className="font-mono text-xs text-muted-foreground">
                  {current.patient.external_patient_id} · {current.patient.gender} ·{" "}
                  {current.encounter.status} · {current.encounter.chief_complaint}
                </p>
              </div>
            ) : activeEncounterId && assessment.isLoading ? (
              <p className="text-xs text-muted-foreground">Loading persisted encounter…</p>
            ) : null}
            {assessment.error ? (
              <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-xs text-destructive">
                {errorMessage(assessment.error)}
              </section>
            ) : null}

            {tab === "Overview" ? (
              current ? (
                <>
                  <div id="demo-reassessment">
                    <VitalsStrip vitals={vitals} />
                  </div>
                  <div id="demo-assessment" className="rounded-lg">
                    <AssessmentOverview
                      assessment={current}
                      queueEntry={queueForEncounter}
                      onQueueStatus={(status) => {
                        if (queueForEncounter?.id) {
                          statusMutation.mutate({ queueId: queueForEncounter.id, status });
                        }
                      }}
                      statusLoading={statusMutation.isPending}
                    />
                  </div>
                  <div className="grid gap-4 xl:grid-cols-2">
                    <ClinicalSummaryCard assessment={current} />
                    <ExplainabilityPanel features={current.explanation?.feature_contributions} />
                  </div>
                </>
              ) : (
                <EmptyWorkspace onOpen={() => setTab("Inputs")} />
              )
            ) : null}

            {tab === "Reasoning" ? (
              current ? (
                <div id="demo-reasoning" className="grid gap-4 rounded-lg xl:grid-cols-[1.6fr_1fr]">
                  <ReasoningTrace reasoning={current.clinical_reasoning} />
                  <div className="space-y-4">
                    <div id="demo-explainability" className="rounded-lg">
                      <ExplainabilityPanel features={current.explanation?.feature_contributions} />
                    </div>
                    <RuleTracePanel triage={current.triage} priority={current.priority} />
                  </div>
                </div>
              ) : (
                <EmptyWorkspace onOpen={() => setTab("Inputs")} />
              )
            ) : null}

            {tab === "Inputs" ? (
              <ClinicalIntakePanel
                initialPatientId={activePatientId}
                encounterId={activeEncounterId}
                encounter={current?.encounter}
                onEncounterChange={selectEncounter}
                onChanged={refresh}
                onAssessmentComplete={async () => {
                  await refresh();
                  setTab("Overview");
                }}
              />
            ) : null}
          </div>
        </main>
      </div>
      <JudgeDemoPanel
        open={judgeOpen}
        onClose={() => setJudgeOpen(false)}
        onNavigate={showDemoTarget}
      />
    </div>
  );
}

function EmptyWorkspace({ onOpen }) {
  return (
    <section className="rounded-lg border border-dashed border-border bg-card p-10 text-center">
      <p className="text-sm font-medium">No encounter selected</p>
      <p className="mt-2 text-xs text-muted-foreground">
        Register or search for a patient, then create or open an encounter.
      </p>
      <button
        onClick={onOpen}
        className="mt-4 rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-xs font-medium text-primary"
      >
        Open clinical inputs
      </button>
    </section>
  );
}

function mapVitals(readings) {
  if (!readings.length) return [];
  const definitions = [
    ["heart_rate", "Heart rate", "bpm"],
    ["spo2", "SpO2", "%"],
    ["systolic_bp", "Blood pressure", "mmHg"],
    ["temperature", "Temperature", "°C"],
    ["respiratory_rate", "Resp rate", "/min"],
  ];
  const latest = readings[readings.length - 1];
  return definitions.flatMap(([key, label, unit]) => {
    const series = readings.map((item) => item[key]).filter((value) => value != null);
    if (latest[key] == null) return [];
    return [
      {
        key,
        label,
        unit,
        value: latest[key],
        display:
          key === "systolic_bp" && latest.diastolic_bp != null
            ? `${latest.systolic_bp}/${latest.diastolic_bp}`
            : String(latest[key]),
        series,
        source: latest.source,
        measuredAt: latest.measured_at,
      },
    ];
  });
}
