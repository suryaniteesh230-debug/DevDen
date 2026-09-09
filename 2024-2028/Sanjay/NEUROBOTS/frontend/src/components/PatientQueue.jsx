import { useMemo, useState } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import PatientQueueItem from "./PatientQueueItem";

const FILTERS = [
  ["ALL", "All"],
  ["URGENT", "Urgent"],
  ["TREND", "Deteriorating"],
];

export default function PatientQueue({
  patients,
  pendingPatients = [],
  selectedId,
  onSelect,
  onSelectPending,
  loading,
  error,
  onClose,
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("ALL");
  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return patients.filter((patient) => {
      const matchesText =
        !term ||
        `${patient.patient_display.display_name} ${patient.patient_display.chief_complaint}`
          .toLowerCase()
          .includes(term);
      const matchesFilter =
        filter === "ALL" ||
        (filter === "URGENT" &&
          ["CRITICAL", "VERY_HIGH", "HIGH"].includes(patient.priority_band)) ||
        (filter === "TREND" && patient.deterioration_status === "DETECTED");
      return matchesText && matchesFilter;
    });
  }, [patients, query, filter]);
  const visiblePending = useMemo(() => {
    if (filter !== "ALL") return [];
    const term = query.trim().toLowerCase();
    return pendingPatients.filter(
      (patient) =>
        !term ||
        `${patient.patient_display.display_name} ${patient.patient_display.chief_complaint}`
          .toLowerCase()
          .includes(term),
    );
  }, [pendingPatients, query, filter]);
  const visibleCount = visible.length + visiblePending.length;
  const totalCount = patients.length + pendingPatients.length;

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-surface">
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Live patient queue
            </h2>
            <p className="mt-0.5 font-mono text-[9px] text-muted-foreground">
              server-ranked · refreshes every 5s
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-primary/10 px-2 py-1 font-mono text-[11px] font-semibold text-primary">
              {visibleCount}/{totalCount}
            </span>
            {onClose ? (
              <button
                type="button"
                onClick={onClose}
                className="pressable flex h-7 w-7 items-center justify-center rounded-md border border-border text-muted-foreground lg:hidden"
                aria-label="Close patient queue"
              >
                <X size={13} />
              </button>
            ) : null}
          </div>
        </div>

        <div className="relative mt-3">
          <Search
            size={13}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter name or complaint"
            className="w-full rounded-md border border-border bg-card py-2 pr-2 pl-8 text-[11px] outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/10"
          />
        </div>
        <div className="mt-2 flex gap-1">
          {FILTERS.map(([value, label]) => (
            <button
              type="button"
              key={value}
              onClick={() => setFilter(value)}
              className={`pressable rounded-md px-2 py-1 text-[9px] font-semibold ${filter === value ? "bg-foreground text-background" : "bg-card text-muted-foreground hover:text-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto border-t border-border">
        {loading ? (
          <div className="space-y-2 p-3">
            {[0, 1, 2].map((item) => (
              <div key={item} className="loading-shimmer h-24 rounded-lg bg-muted" />
            ))}
          </div>
        ) : null}
        {error ? <p className="px-4 py-5 text-xs text-destructive">{error}</p> : null}
        {!loading && !error && visibleCount === 0 ? (
          <div className="px-5 py-10 text-center">
            <SlidersHorizontal size={18} className="mx-auto text-muted-foreground" />
            <p className="mt-3 text-xs font-medium">No matching patients</p>
            <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
              Clear the filters or open Inputs to register and assess an encounter.
            </p>
          </div>
        ) : null}
        {visible.map((patient, index) => (
          <PatientQueueItem
            key={patient.id}
            patient={patient}
            selected={patient.id === selectedId}
            onSelect={(id) => {
              onSelect(id);
              onClose?.();
            }}
            index={index}
          />
        ))}
        {visiblePending.length ? (
          <div className="border-y border-border bg-muted/30 px-4 py-2 font-mono text-[9px] font-semibold tracking-wide text-muted-foreground uppercase">
            Pending intake · not yet ranked
          </div>
        ) : null}
        {visiblePending.map((patient, index) => (
          <PatientQueueItem
            key={patient.id}
            patient={patient}
            pending
            selected={patient.id === selectedId}
            onSelect={(id) => {
              onSelectPending(id);
              onClose?.();
            }}
            index={visible.length + index}
          />
        ))}
      </div>
    </div>
  );
}
