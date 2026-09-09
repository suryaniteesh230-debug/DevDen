import VitalCard from "./VitalCard";

export default function VitalsStrip({ vitals }) {
  if (!vitals || vitals.length === 0) return null;

  return (
    <section
      aria-label="Vital signs"
      className="stagger-grid grid grid-cols-2 gap-3 lg:grid-cols-5"
    >
      {vitals.map((vital) => (
        <VitalCard key={vital.key} vital={vital} />
      ))}
    </section>
  );
}
