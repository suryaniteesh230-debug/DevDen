import { useState } from "react";

export default function ClinicalSummaryCard({ assessment }) {
  const [selectedSymptom, setSelectedSymptom] = useState(null);
  if (!assessment) return null;
  const { patient, encounter } = assessment;
  const presentSymptoms = encounter.symptoms.filter((item) => item.present);

  return (
    <section className="interactive-card rounded-lg border border-border bg-card p-4">
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        Clinical summary
      </h3>

      <p className="mt-2 text-sm font-medium">{encounter.chief_complaint}</p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {presentSymptoms.map((symptom) => (
          <button
            type="button"
            onClick={() => setSelectedSymptom(selectedSymptom?.id === symptom.id ? null : symptom)}
            key={symptom.id}
            className={`pressable rounded-md border px-2 py-1 text-[11px] ${selectedSymptom?.id === symptom.id ? "border-primary bg-primary/10 text-primary" : "border-border bg-surface-raised text-muted-foreground hover:border-primary/30"}`}
          >
            {symptom.name} · {symptom.source}
          </button>
        ))}
      </div>

      {selectedSymptom ? (
        <div className="view-enter mt-2 rounded-md border border-primary/20 bg-primary/5 p-2.5 text-[10px] leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">{selectedSymptom.name}</span> · severity{" "}
          {selectedSymptom.severity ?? "not recorded"} · duration{" "}
          {selectedSymptom.duration || "not recorded"} · source{" "}
          <span className="font-mono text-primary">{selectedSymptom.source}</span>
        </div>
      ) : null}

      <div className="mt-4 border-t border-border pt-3">
        <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          Encounter context
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          {patient.first_name} {patient.last_name} · {encounter.encounter_type} ·{" "}
          {encounter.lab_results.length} lab observations · {encounter.vital_signs.length} vital
          readings
        </p>
        {encounter.clinician_notes ? (
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
            {encounter.clinician_notes}
          </p>
        ) : null}
      </div>
    </section>
  );
}
