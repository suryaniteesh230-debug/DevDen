const BANDS = {
  CRITICAL: {
    label: "Critical",
    text: "text-esi-1",
    ring: "border-esi-1/50",
    bg: "bg-esi-1/15",
    dot: "bg-esi-1",
  },
  VERY_HIGH: {
    label: "Very high",
    text: "text-esi-2",
    ring: "border-esi-2/50",
    bg: "bg-esi-2/15",
    dot: "bg-esi-2",
  },
  HIGH: {
    label: "High",
    text: "text-esi-3",
    ring: "border-esi-3/50",
    bg: "bg-esi-3/15",
    dot: "bg-esi-3",
  },
  MODERATE: {
    label: "Moderate",
    text: "text-esi-4",
    ring: "border-esi-4/50",
    bg: "bg-esi-4/15",
    dot: "bg-esi-4",
  },
  ROUTINE: {
    label: "Routine",
    text: "text-esi-5",
    ring: "border-esi-5/50",
    bg: "bg-esi-5/15",
    dot: "bg-esi-5",
  },
};

export function priorityStyle(band) {
  return BANDS[band] || BANDS.ROUTINE;
}

export default function PriorityBadge({ band, size = "sm" }) {
  const style = priorityStyle(band);
  const sizing = size === "lg" ? "text-sm px-2.5 py-1 gap-2" : "text-[11px] px-1.5 py-0.5 gap-1.5";
  return (
    <span
      className={`inline-flex items-center rounded-md border font-mono font-medium tracking-tight transition-transform duration-200 hover:scale-105 ${sizing} ${style.bg} ${style.ring} ${style.text}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${style.dot} ${band === "CRITICAL" ? "live-dot" : ""}`}
      />
      {style.label}
    </span>
  );
}
