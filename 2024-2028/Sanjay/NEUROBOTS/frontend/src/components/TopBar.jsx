import { LogOut, Menu, Radio, RefreshCw, Server, Sparkles } from "lucide-react";

export default function TopBar({
  waitingCount,
  backendOnline,
  refreshing,
  onRefresh,
  onOpenQueue,
  onOpenJudgeMode,
  staffUser,
  onLogout,
}) {
  return (
    <header className="relative z-40 flex flex-wrap items-center gap-3 border-b border-border bg-surface/95 px-4 py-3 backdrop-blur-xl md:px-5">
      <button
        type="button"
        onClick={onOpenQueue}
        className="pressable flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground lg:hidden"
        aria-label="Open patient queue"
      >
        <Menu size={15} />
      </button>

      <div className="flex items-center gap-2.5">
        <span className="brand-beacon interactive-card relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-lg bg-primary/15 text-primary">
          <img src="/favicon.ico" alt="NextCare logo" className="relative z-10 h-5 w-5" />
          <span className="absolute inset-x-0 bottom-0 h-px bg-primary/40" />
        </span>
        <div className="leading-tight">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold tracking-tight">NextCare Clinical Console</p>
            <span className="hidden rounded border border-primary/25 bg-primary/8 px-1.5 py-0.5 text-[8px] font-bold tracking-wider text-primary uppercase sm:inline">
              Edge-first
            </span>
          </div>
          <p className="font-mono text-[10px] text-muted-foreground">
            auditable multi-agent decision support
          </p>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={onOpenJudgeMode}
          className="pressable group inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-2.5 py-2 text-[10px] font-semibold text-primary hover:bg-primary/15"
        >
          <Sparkles
            size={13}
            className="transition-transform group-hover:rotate-12 group-hover:scale-110"
          />
          <span className="hidden sm:inline">Judge demo</span>
        </button>

        <button
          type="button"
          onClick={onRefresh}
          className="pressable flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-primary"
          aria-label="Refresh live clinical data"
        >
          <RefreshCw size={13} className={refreshing ? "animate-spin text-primary" : ""} />
        </button>

        <div className="hidden items-center gap-2 rounded-md border border-border bg-surface-raised px-3 py-1.5 sm:flex">
          <Radio size={13} className="text-primary" />
          <span className="font-mono text-lg leading-none font-semibold">{waitingCount}</span>
          <span className="text-[11px] text-muted-foreground">waiting</span>
        </div>

        <div className="flex items-center gap-2 rounded-md border border-border bg-surface-raised px-2.5 py-2">
          <span className="relative flex h-2 w-2">
            {backendOnline ? (
              <>
                <span className="live-dot absolute inline-flex h-full w-full rounded-full bg-primary/55" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
              </>
            ) : (
              <span className="relative inline-flex h-2 w-2 rounded-full bg-destructive" />
            )}
          </span>
          <Server size={12} className={backendOnline ? "text-primary" : "text-destructive"} />
          <span className="hidden text-[10px] text-muted-foreground xl:inline">
            {backendOnline ? "Local backend connected" : "Backend unavailable"}
          </span>
        </div>

        <div className="hidden leading-tight lg:block">
          <p className="max-w-36 truncate text-[10px] font-medium">{staffUser.full_name}</p>
          <p className="font-mono text-[9px] text-muted-foreground">{staffUser.role}</p>
        </div>

        <button
          type="button"
          onClick={onLogout}
          className="pressable flex h-8 w-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-destructive"
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut size={13} />
        </button>
      </div>
    </header>
  );
}
