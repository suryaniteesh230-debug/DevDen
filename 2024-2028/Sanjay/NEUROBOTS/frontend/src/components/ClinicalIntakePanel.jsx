import {
  CheckCircle2,
  ChevronDown,
  ClipboardPlus,
  LoaderCircle,
  Search,
  Sparkles,
  UserPlus,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import DocumentUploadCard from "./DocumentUploadCard";
import SpeechInputCard from "./SpeechInputCard";

const emptyRegistration = {
  external_patient_id: "",
  first_name: "",
  last_name: "",
  date_of_birth: "",
  gender: "",
  phone_number: "",
};

const SYMPTOM_OPTIONS = [
  "chest pain",
  "chest pressure",
  "shortness of breath",
  "sweating",
  "nausea",
  "vomiting",
  "dizziness",
  "palpitations",
  "fatigue",
  "syncope",
  "jaw pain",
  "arm pain",
  "back pain",
  "abdominal pain",
];

const DURATION_OPTIONS = [
  "Less than 5 minutes",
  "5–15 minutes",
  "15–30 minutes",
  "30–60 minutes",
  "1–3 hours",
  "3–12 hours",
  "More than 12 hours",
  "Intermittent",
  "Unknown",
];

const COMPLAINT_OPTIONS = [
  "Chest pain",
  "Chest pressure with shortness of breath",
  "Shortness of breath",
  "Palpitations",
  "Syncope or near-syncope",
  "Dizziness and weakness",
  "Nausea with sweating",
];

const LAB_CATALOG = [
  { value: "troponin", label: "Troponin", units: ["ng/mL", "ng/L", "µg/L"] },
  { value: "ck_mb", label: "CK-MB", units: ["ng/mL", "U/L"] },
  { value: "blood_sugar", label: "Blood sugar / glucose", units: ["mg/dL", "mmol/L"] },
  { value: "creatinine", label: "Creatinine", units: ["mg/dL", "µmol/L"] },
  { value: "potassium", label: "Potassium", units: ["mmol/L", "mEq/L"] },
  { value: "haemoglobin", label: "Haemoglobin", units: ["g/dL", "g/L"] },
  { value: "WBC", label: "White blood cell count", units: ["10^9/L", "cells/µL"] },
];

const ALL_LAB_UNITS = [...new Set(LAB_CATALOG.flatMap((item) => item.units))];

export default function ClinicalIntakePanel({
  initialPatientId,
  encounterId,
  encounter,
  onEncounterChange,
  onChanged,
  onAssessmentComplete,
}) {
  const [patientId, setPatientId] = useState(initialPatientId || "");
  const [history, setHistory] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [registration, setRegistration] = useState(emptyRegistration);
  const [showRegistration, setShowRegistration] = useState(false);
  const [complaint, setComplaint] = useState("");
  const [symptom, setSymptom] = useState({ name: "", severity: "", duration: "", present: true });
  const [vitals, setVitals] = useState({
    heart_rate: "",
    systolic_bp: "",
    diastolic_bp: "",
    spo2: "",
    respiratory_rate: "",
    temperature: "",
  });
  const [lab, setLab] = useState({ test_name: "", value: "", unit: "" });
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (initialPatientId) setPatientId(initialPatientId);
  }, [initialPatientId]);

  useEffect(() => {
    if (!patientId) {
      setHistory(null);
      return;
    }
    api
      .patientHistory(patientId)
      .then(setHistory)
      .catch((caught) => setError(errorMessage(caught)));
  }, [patientId, encounterId]);

  const act = async (name, action, success, refreshAfter = true) => {
    setBusy(name);
    setError("");
    setMessage("");
    try {
      const value = await action();
      if (refreshAfter) {
        try {
          await onChanged?.();
        } catch (refreshError) {
          setError(`Saved, but the screen could not refresh: ${errorMessage(refreshError)}`);
        }
      }
      setMessage(success);
      return value;
    } catch (caught) {
      setError(errorMessage(caught));
      return null;
    } finally {
      setBusy("");
    }
  };

  const search = async (event) => {
    event.preventDefault();
    const found = await act(
      "search",
      () => api.searchPatients(query),
      "Patient search complete.",
      false,
    );
    if (found) setResults(found);
  };

  const register = async (event) => {
    event.preventDefault();
    const created = await act(
      "register",
      () => api.createPatient({ ...registration, phone_number: registration.phone_number || null }),
      "Patient registered.",
      true,
    );
    if (created) {
      setPatientId(created.id);
      setResults([created]);
      setRegistration(emptyRegistration);
      setShowRegistration(false);
    }
  };

  const createEncounter = async (event) => {
    event.preventDefault();
    const created = await act(
      "encounter",
      () =>
        api.createEncounter(patientId, { encounter_type: "emergency", chief_complaint: complaint }),
      "Encounter created.",
      true,
    );
    if (created) {
      onEncounterChange(created.id, patientId);
      setComplaint("");
    }
  };

  const addSymptom = async (event) => {
    event.preventDefault();
    const created = await act(
      "symptom",
      () =>
        api.addSymptom(encounterId, {
          name: symptom.name,
          severity: symptom.severity === "" ? null : Number(symptom.severity),
          duration: symptom.duration || null,
          present: symptom.present,
          source: "MANUAL",
        }),
      "Symptom saved to the database.",
    );
    if (created) setSymptom({ name: "", severity: "", duration: "", present: true });
  };

  const addVitals = async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(
      Object.entries(vitals)
        .filter(([, value]) => value !== "")
        .map(([key, value]) => [key, Number(value)]),
    );
    if (!Object.keys(payload).length) {
      setError("Enter at least one vital-sign measurement before saving.");
      setMessage("");
      return;
    }
    const created = await act(
      "vitals",
      () => api.addVitals(encounterId, { ...payload, source: "MANUAL" }),
      "Vital reading saved to the database.",
    );
    if (created)
      setVitals({
        heart_rate: "",
        systolic_bp: "",
        diastolic_bp: "",
        spo2: "",
        respiratory_rate: "",
        temperature: "",
      });
  };

  const addLab = async (event) => {
    event.preventDefault();
    const created = await act(
      "lab",
      () =>
        api.addLab(encounterId, {
          test_name: lab.test_name,
          value: Number(lab.value),
          unit: lab.unit || null,
          source: "MANUAL",
        }),
      "Lab result saved to the database.",
    );
    if (created) setLab({ test_name: "", value: "", unit: "" });
  };

  const runAssessment = async () => {
    const result = await act(
      "workflow",
      () => api.runWorkflow(encounterId),
      "Assessment completed; persisted results refreshed.",
      false,
    );
    if (result) onAssessmentComplete?.();
  };

  return (
    <div className="space-y-4">
      <section className="interactive-card rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Patient and encounter
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Search an existing patient or register a new record.
            </p>
          </div>
          <button
            onClick={() => setShowRegistration((value) => !value)}
            className="pressable inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/30 hover:text-primary"
          >
            <UserPlus size={13} />
            {showRegistration ? "Close registration" : "New patient"}
          </button>
        </div>
        <form onSubmit={search} className="mt-3 flex gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by patient name"
            className="min-w-0 flex-1 rounded-md border border-border bg-card px-3 py-2 text-xs outline-none focus:border-primary"
          />
          <button
            disabled={busy === "search"}
            className="pressable inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            <Search size={13} />
            Search
          </button>
        </form>
        {results.length ? (
          <div className="stagger-grid mt-3 grid gap-2 md:grid-cols-2">
            {results.map((patient) => (
              <button
                key={patient.id}
                onClick={() => setPatientId(patient.id)}
                className={`pressable rounded-md border p-3 text-left ${patient.id === patientId ? "border-primary bg-primary/5 shadow-sm" : "border-border bg-card hover:border-primary/30"}`}
              >
                <p className="text-xs font-medium">
                  {patient.first_name} {patient.last_name}
                </p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {patient.external_patient_id} · {patient.gender}
                </p>
              </button>
            ))}
          </div>
        ) : null}
        {showRegistration ? (
          <form
            onSubmit={register}
            className="view-enter mt-4 grid gap-2 border-t border-border pt-4 md:grid-cols-2 xl:grid-cols-3"
          >
            {Object.entries({
              external_patient_id: "External patient ID",
              first_name: "First name",
              last_name: "Last name",
              date_of_birth: "Date of birth",
              gender: "Gender",
              phone_number: "Phone (optional)",
            }).map(([key, label]) => (
              <label key={key} className="group text-[11px] text-muted-foreground">
                <span className="transition-colors group-focus-within:text-primary">{label}</span>
                {key === "gender" ? (
                  <div className="relative mt-1">
                    <select
                      required
                      value={registration.gender}
                      onChange={(event) =>
                        setRegistration((value) => ({ ...value, gender: event.target.value }))
                      }
                      className="categorical-control w-full appearance-none rounded-md border border-border bg-card px-2.5 py-2 pr-8 text-xs text-foreground outline-none focus:border-primary"
                    >
                      <option value="" disabled>
                        Select recorded gender
                      </option>
                      <option value="female">Female</option>
                      <option value="male">Male</option>
                      <option value="other">Other</option>
                      <option value="unknown">Unknown / not stated</option>
                    </select>
                    <ChevronDown
                      size={12}
                      className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground transition-transform group-focus-within:rotate-180 group-focus-within:text-primary"
                    />
                  </div>
                ) : (
                  <input
                    required={key !== "phone_number"}
                    type={
                      key === "date_of_birth" ? "date" : key === "phone_number" ? "tel" : "text"
                    }
                    value={registration[key]}
                    onChange={(event) =>
                      setRegistration((value) => ({ ...value, [key]: event.target.value }))
                    }
                    className="input-alive mt-1 w-full rounded-md border border-border bg-card px-2.5 py-2 text-xs text-foreground outline-none focus:border-primary"
                  />
                )}
              </label>
            ))}
            <button
              disabled={busy === "register"}
              className="pressable self-end rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground disabled:opacity-50"
            >
              Register patient
            </button>
          </form>
        ) : null}
        {history ? (
          <div className="mt-4 border-t border-border pt-4">
            <p className="text-xs font-medium">
              Selected: {history.patient.first_name} {history.patient.last_name}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {history.encounters.map((item) => (
                <button
                  key={item.id}
                  onClick={() => onEncounterChange(item.id, patientId)}
                  className={`pressable rounded-md border px-2.5 py-1.5 text-[11px] ${item.id === encounterId ? "border-primary bg-primary/10 text-primary shadow-sm" : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground"}`}
                >
                  {new Date(item.started_at).toLocaleDateString()} · {item.chief_complaint}
                </button>
              ))}
            </div>
            <form onSubmit={createEncounter} className="mt-3 flex gap-2">
              <input
                required
                list="chief-complaint-options"
                value={complaint}
                onChange={(event) => setComplaint(event.target.value)}
                placeholder="Chief complaint for a new emergency encounter"
                className="input-alive min-w-0 flex-1 rounded-md border border-border bg-card px-3 py-2 text-xs outline-none focus:border-primary"
              />
              <datalist id="chief-complaint-options">
                {COMPLAINT_OPTIONS.map((value) => (
                  <option key={value} value={value} />
                ))}
              </datalist>
              <button
                disabled={busy === "encounter"}
                className="pressable inline-flex items-center gap-1.5 rounded-md border border-primary/40 bg-primary/10 px-3 py-2 text-xs font-medium text-primary disabled:opacity-50"
              >
                <ClipboardPlus size={13} />
                Create encounter
              </button>
            </form>
          </div>
        ) : null}
      </section>

      {encounterId ? (
        <>
          <section
            id="demo-observations"
            className="stagger-grid grid scroll-mt-20 gap-3 rounded-lg xl:grid-cols-3"
          >
            <ObservationCard title="Symptom">
              <form onSubmit={addSymptom} className="space-y-2">
                <SuggestionField
                  id="symptom-name"
                  required
                  placeholder="Choose or type a symptom"
                  value={symptom.name}
                  options={SYMPTOM_OPTIONS}
                  onChange={(value) => setSymptom((item) => ({ ...item, name: value }))}
                />
                <div className="grid grid-cols-2 gap-2">
                  <SelectField
                    placeholder="Severity"
                    value={symptom.severity}
                    options={Array.from({ length: 11 }, (_, value) => [
                      String(value),
                      `${value} / 10`,
                    ])}
                    onChange={(value) => setSymptom((item) => ({ ...item, severity: value }))}
                  />
                  <SuggestionField
                    id="symptom-duration"
                    placeholder="Choose duration"
                    value={symptom.duration}
                    options={DURATION_OPTIONS}
                    onChange={(value) => setSymptom((item) => ({ ...item, duration: value }))}
                  />
                </div>
                <div
                  className="grid grid-cols-2 gap-1 rounded-md bg-surface p-1"
                  role="group"
                  aria-label="Symptom assertion"
                >
                  <button
                    type="button"
                    onClick={() => setSymptom((item) => ({ ...item, present: true }))}
                    className={`pressable rounded px-2 py-1.5 text-[10px] font-medium ${symptom.present ? "bg-card text-primary shadow-sm" : "text-muted-foreground"}`}
                  >
                    Present
                  </button>
                  <button
                    type="button"
                    onClick={() => setSymptom((item) => ({ ...item, present: false }))}
                    className={`pressable rounded px-2 py-1.5 text-[10px] font-medium ${!symptom.present ? "bg-card text-primary shadow-sm" : "text-muted-foreground"}`}
                  >
                    Explicitly absent
                  </button>
                </div>
                <SaveButton busy={busy === "symptom"}>Save symptom</SaveButton>
              </form>
              <SavedRecords
                items={encounter?.symptoms || []}
                empty="No symptoms saved yet."
                renderItem={(item) => (
                  <>
                    <span className="font-medium text-foreground">
                      {item.present ? item.name : `No ${item.name}`}
                    </span>
                    <span>
                      {item.severity == null ? "severity not recorded" : `${item.severity}/10`}
                      {item.duration ? ` · ${item.duration}` : ""}
                    </span>
                  </>
                )}
              />
            </ObservationCard>
            <ObservationCard title="Vital signs">
              <form onSubmit={addVitals} className="grid grid-cols-2 gap-2">
                {[
                  ["heart_rate", "Heart rate", "bpm", 1, 300],
                  ["systolic_bp", "Systolic BP", "mmHg", 1, 300],
                  ["diastolic_bp", "Diastolic BP", "mmHg", 1, 250],
                  ["spo2", "SpO₂", "%", 0, 100],
                  ["respiratory_rate", "Respiratory rate", "/min", 1, 100],
                  ["temperature", "Temperature", "°C", 20, 50],
                ].map(([key, label, unit, min, max]) => (
                  <VitalField
                    key={key}
                    label={label}
                    unit={unit}
                    min={min}
                    max={max}
                    value={vitals[key]}
                    onChange={(value) => setVitals((item) => ({ ...item, [key]: value }))}
                  />
                ))}
                <div className="col-span-2">
                  <SaveButton busy={busy === "vitals"}>Save vital reading</SaveButton>
                </div>
              </form>
              <SavedRecords
                items={encounter?.vital_signs || []}
                empty="No vital readings saved yet."
                renderItem={(item) => (
                  <>
                    <span className="font-medium text-foreground">{formatVitalReading(item)}</span>
                    <span>{new Date(item.measured_at).toLocaleString()}</span>
                  </>
                )}
              />
            </ObservationCard>
            <ObservationCard title="Laboratory observation">
              <form onSubmit={addLab} className="space-y-2">
                <SuggestionField
                  id="lab-test-name"
                  required
                  placeholder="Choose or type a test"
                  value={lab.test_name}
                  options={LAB_CATALOG.map((item) => ({ value: item.value, label: item.label }))}
                  onChange={(value) => {
                    const match = LAB_CATALOG.find((item) => item.value === value);
                    setLab((item) => ({
                      ...item,
                      test_name: value,
                      unit: match?.units[0] ?? item.unit,
                    }));
                  }}
                />
                <div className="grid grid-cols-2 gap-2">
                  <Field
                    required
                    type="number"
                    step="any"
                    placeholder="Value"
                    value={lab.value}
                    onChange={(value) => setLab((item) => ({ ...item, value }))}
                  />
                  <SuggestionField
                    id="lab-unit"
                    placeholder="Unit"
                    value={lab.unit}
                    options={
                      LAB_CATALOG.find((item) => item.value === lab.test_name)?.units ||
                      ALL_LAB_UNITS
                    }
                    onChange={(value) => setLab((item) => ({ ...item, unit: value }))}
                  />
                </div>
                <SaveButton busy={busy === "lab"}>Save lab result</SaveButton>
              </form>
              <SavedRecords
                items={encounter?.lab_results || []}
                empty="No lab results saved yet."
                renderItem={(item) => (
                  <>
                    <span className="font-medium text-foreground">{item.test_name}</span>
                    <span>
                      {item.value} {item.unit || ""}
                    </span>
                  </>
                )}
              />
            </ObservationCard>
          </section>
          <section
            id="demo-multimodal"
            className="interactive-card scroll-mt-20 rounded-lg border border-border bg-surface p-4"
          >
            <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Multimodal input tray
            </h3>
            <div className="mt-3 grid gap-3 xl:grid-cols-2">
              <DocumentUploadCard encounterId={encounterId} onUploaded={onChanged} />
              <SpeechInputCard encounterId={encounterId} onUploaded={onChanged} />
            </div>
          </section>
          <section className="interactive-card relative overflow-hidden rounded-lg border border-primary/30 bg-primary/5 p-4">
            {busy === "workflow" ? (
              <span className="loading-shimmer absolute inset-0 bg-primary/5" aria-hidden="true" />
            ) : null}
            <div className="relative flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="flex items-center gap-2 text-sm font-medium">
                  <Sparkles
                    size={14}
                    className={busy === "workflow" ? "text-primary live-dot" : "text-primary"}
                  />
                  Run multi-agent clinical assessment
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Local cardiac risk, provisional triage, SHAP and priority remain available if
                  cloud reasoning is unavailable.
                </p>
              </div>
              <button
                onClick={runAssessment}
                disabled={busy === "workflow"}
                className="pressable inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground disabled:opacity-60"
              >
                {busy === "workflow" ? (
                  <LoaderCircle size={13} className="animate-spin" />
                ) : (
                  <Sparkles size={13} />
                )}
                {busy === "workflow" ? "Agents assessing…" : "Run assessment"}
              </button>
            </div>
            {busy === "workflow" ? <WorkflowProgress /> : null}
          </section>
        </>
      ) : (
        <section className="rounded-lg border border-dashed border-border bg-card p-8 text-center text-xs text-muted-foreground">
          Select or create an encounter to enter clinical observations.
        </section>
      )}
      {message ? (
        <div
          role="status"
          className="view-enter flex items-center gap-2 rounded-lg border border-primary/25 bg-primary/8 px-3 py-2 text-xs text-primary"
        >
          <CheckCircle2 size={14} /> {message}
        </div>
      ) : null}
      {error ? (
        <p
          role="alert"
          className="view-enter rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2 text-xs text-destructive"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ObservationCard({ title, children }) {
  return (
    <article className="interactive-card rounded-lg border border-border bg-card p-4">
      <h3 className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </h3>
      {children}
    </article>
  );
}
function Field({ onChange, ...props }) {
  return (
    <input
      {...props}
      onChange={(event) => onChange(event.target.value)}
      className="input-alive w-full rounded-md border border-border bg-surface px-2.5 py-2 text-xs outline-none focus:border-primary"
    />
  );
}

function VitalField({ label, unit, min, max, onChange, value }) {
  return (
    <label className="group block">
      <span className="mb-1 block text-[9px] font-medium text-muted-foreground transition-colors group-focus-within:text-primary">
        {label}
      </span>
      <span className="relative block">
        <input
          type="number"
          step="any"
          min={min}
          max={max}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="input-alive w-full rounded-md border border-border bg-surface px-2.5 py-2 pr-12 text-xs outline-none focus:border-primary"
        />
        <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 font-mono text-[8px] text-muted-foreground">
          {unit}
        </span>
      </span>
    </label>
  );
}

function SuggestionField({ id, options, onChange, ...props }) {
  const normalized = options.map((item) =>
    typeof item === "string" ? { value: item, label: item } : item,
  );
  return (
    <div className="group relative">
      <input
        {...props}
        list={`${id}-options`}
        onChange={(event) => onChange(event.target.value)}
        className="input-alive w-full rounded-md border border-border bg-surface px-2.5 py-2 pr-8 text-xs outline-none focus:border-primary"
      />
      <ChevronDown
        size={12}
        className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground transition-all group-focus-within:rotate-180 group-focus-within:text-primary"
      />
      <datalist id={`${id}-options`}>
        {normalized.map((item) => (
          <option key={item.value} value={item.value} label={item.label} />
        ))}
      </datalist>
    </div>
  );
}

function SelectField({ placeholder, options, onChange, ...props }) {
  return (
    <div className="group relative">
      <select
        {...props}
        onChange={(event) => onChange(event.target.value)}
        className="categorical-control w-full appearance-none rounded-md border border-border bg-surface px-2.5 py-2 pr-8 text-xs outline-none focus:border-primary"
      >
        <option value="">{placeholder}</option>
        {options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={12}
        className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground transition-all group-focus-within:rotate-180 group-focus-within:text-primary"
      />
    </div>
  );
}
function SaveButton({ busy, children }) {
  return (
    <button
      disabled={busy}
      className="pressable w-full rounded-md border border-primary/40 bg-primary/10 px-2.5 py-2 text-[11px] font-medium text-primary hover:bg-primary/15 disabled:opacity-50"
    >
      {busy ? "Saving…" : children}
    </button>
  );
}

function SavedRecords({ items, empty, renderItem }) {
  const recent = items.slice(-3).reverse();
  return (
    <div className="mt-3 border-t border-border pt-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[9px] font-semibold tracking-wide text-muted-foreground uppercase">
          Persisted records
        </p>
        <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[9px] text-primary">
          {items.length}
        </span>
      </div>
      {recent.length ? (
        <div className="mt-2 space-y-1.5">
          {recent.map((item) => (
            <div
              key={item.id}
              className="flex flex-wrap items-baseline justify-between gap-x-2 rounded-md border border-border bg-surface px-2 py-1.5 text-[10px] text-muted-foreground"
            >
              {renderItem(item)}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-[10px] text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}

function formatVitalReading(item) {
  return [
    item.heart_rate == null ? null : `HR ${item.heart_rate}`,
    item.systolic_bp == null && item.diastolic_bp == null
      ? null
      : `BP ${item.systolic_bp ?? "—"}/${item.diastolic_bp ?? "—"}`,
    item.spo2 == null ? null : `SpO₂ ${item.spo2}%`,
    item.respiratory_rate == null ? null : `RR ${item.respiratory_rate}`,
    item.temperature == null ? null : `Temp ${item.temperature}°C`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function WorkflowProgress() {
  return (
    <div className="relative mt-4 border-t border-primary/15 pt-3">
      <div className="grid grid-cols-4 gap-2 text-center">
        {["Fuse inputs", "Assess risk", "Rank queue", "Explain"].map((label, index) => (
          <div key={label} className="view-enter" style={{ animationDelay: `${index * 120}ms` }}>
            <span
              className="mx-auto block h-1.5 w-1.5 rounded-full bg-primary live-dot"
              style={{ animationDelay: `${index * 160}ms` }}
            />
            <p className="mt-1.5 font-mono text-[8px] text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
