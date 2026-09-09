const ECG_PATH =
  "M0 52 L78 52 L92 50 L104 55 L116 52 L148 52 L162 45 L174 62 L188 52 L216 52 L230 50 L242 14 L255 82 L269 32 L284 52 L342 52 L358 49 L370 54 L384 52 L420 52 L434 46 L446 60 L459 52 L486 52 L500 49 L512 20 L525 76 L539 36 L554 52 L618 52 L632 50 L644 55 L657 52 L688 52 L702 44 L715 63 L728 52 L756 52 L770 49 L782 12 L795 84 L810 30 L826 52 L884 52 L899 49 L912 55 L925 52 L958 52 L972 45 L984 61 L997 52 L1024 52 L1038 49 L1050 18 L1063 79 L1078 34 L1093 52 L1200 52";

export default function EcgOverlay() {
  return (
    <div className="ecg-overlay" aria-hidden="true">
      <svg viewBox="0 0 1200 96" preserveAspectRatio="none" role="presentation" focusable="false">
        <defs>
          <linearGradient id="ecg-fade" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="var(--primary)" stopOpacity="0" />
            <stop offset="0.12" stopColor="var(--primary)" stopOpacity="0.42" />
            <stop offset="0.5" stopColor="var(--primary)" stopOpacity="0.58" />
            <stop offset="0.88" stopColor="var(--primary)" stopOpacity="0.42" />
            <stop offset="1" stopColor="var(--primary)" stopOpacity="0" />
          </linearGradient>
          <filter id="ecg-glow" x="-20%" y="-70%" width="140%" height="240%">
            <feGaussianBlur stdDeviation="2.4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <pattern id="ecg-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path
              d="M 24 0 L 0 0 0 24"
              fill="none"
              stroke="var(--primary)"
              strokeOpacity="0.07"
              strokeWidth="0.6"
            />
          </pattern>
        </defs>
        <rect width="1200" height="96" fill="url(#ecg-grid)" />
        <path className="ecg-baseline" d={ECG_PATH} pathLength="1" />
        <path className="ecg-pulse" d={ECG_PATH} pathLength="1" filter="url(#ecg-glow)" />
      </svg>
      <span className="ecg-caption">decorative live trace</span>
    </div>
  );
}
