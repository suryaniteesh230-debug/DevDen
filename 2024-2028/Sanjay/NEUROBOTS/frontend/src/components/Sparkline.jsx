export default function Sparkline({ series, tone = "muted", width = 96, height = 26 }) {
  if (!series || series.length < 2) return null;

  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const step = width / (series.length - 1);

  const points = series
    .map(
      (value, i) =>
        `${(i * step).toFixed(1)},${(height - ((value - min) / span) * (height - 4) - 2).toFixed(1)}`,
    )
    .join(" ");

  const stroke = tone === "alert" ? "var(--esi-1)" : "var(--primary)";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
    >
      <polyline
        className="sparkline-draw"
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={tone === "alert" ? 0.95 : 0.7}
      />
    </svg>
  );
}
