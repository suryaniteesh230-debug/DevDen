import { ChevronDown } from "lucide-react";

export default function ReasoningStep({ index, title, subtitle, open, onToggle, children }) {
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="pressable group flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-raised/50"
      >
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border font-mono text-[11px] transition-all ${open ? "border-primary/35 bg-primary/10 text-primary" : "border-border bg-surface-raised text-muted-foreground group-hover:text-primary"}`}
        >
          {index}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{title}</span>
          {subtitle ? (
            <span className="block truncate text-[11px] text-muted-foreground">{subtitle}</span>
          ) : null}
        </span>
        <ChevronDown
          size={15}
          className={`shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      <div className="smooth-collapse" data-open={open}>
        <div>
          <div className="px-4 pb-4 pl-13">{children}</div>
        </div>
      </div>
    </div>
  );
}
