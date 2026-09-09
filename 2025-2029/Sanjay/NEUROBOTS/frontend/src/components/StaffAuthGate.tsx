import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, LockKeyhole, ShieldCheck, Stethoscope } from "lucide-react";

import TriageDashboard from "@/components/TriageDashboard";
import { api, AUTH_EXPIRED_EVENT, errorMessage, type StaffUser } from "@/lib/api";

type AuthState =
  | { status: "checking"; staff: null }
  | { status: "signed_out"; staff: null }
  | { status: "authenticated"; staff: StaffUser };

export default function StaffAuthGate() {
  const queryClient = useQueryClient();
  const [auth, setAuth] = useState<AuthState>({ status: "checking", staff: null });
  const [showLoginSplash, setShowLoginSplash] = useState(false);

  useEffect(() => {
    let active = true;

    const expireSession = () => {
      api.logout();
      queryClient.clear();
      if (active) {
        setShowLoginSplash(true);
        setAuth({ status: "signed_out", staff: null });
      }
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, expireSession);

    if (!api.hasStaffSession()) {
      setShowLoginSplash(true);
      setAuth({ status: "signed_out", staff: null });
    } else {
      api
        .currentStaff()
        .then((staff) => {
          if (active) setAuth({ status: "authenticated", staff });
        })
        .catch(expireSession);
    }

    return () => {
      active = false;
      window.removeEventListener(AUTH_EXPIRED_EVENT, expireSession);
    };
  }, [queryClient]);

  useEffect(() => {
    if (!showLoginSplash) return;
    const timer = window.setTimeout(() => setShowLoginSplash(false), 4400);
    return () => window.clearTimeout(timer);
  }, [showLoginSplash]);

  if (auth.status === "checking") return <StaffSessionCheck />;
  if (auth.status === "signed_out" && showLoginSplash) return <LoginSplash />;
  if (auth.status === "signed_out") {
    return (
      <MedicalStaffLogin onAuthenticated={(staff) => setAuth({ status: "authenticated", staff })} />
    );
  }
  return (
    <TriageDashboard
      staffUser={auth.staff}
      onLogout={() => {
        api.logout();
        queryClient.clear();
        setAuth({ status: "signed_out", staff: null });
      }}
    />
  );
}

function MedicalStaffLogin({ onAuthenticated }: { onAuthenticated: (staff: StaffUser) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const session = await api.login(email, password);
      onAuthenticated(session.staff);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="clinical-ambient flex min-h-screen items-center justify-center bg-background px-4 py-10 text-foreground">
      <div className="view-enter w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-3">
          
            <img src="/favicon.ico" alt="NextCare logo" className="relative z-10 h-14 w-14 animate-pulse" />
            
          
          <div>
            <p className="text-lg font-semibold tracking-tight">NextCare</p>
            <p className="font-mono text-[10px] text-muted-foreground">
              clinical decision-support console
            </p>
          </div>
        </div>

        <section className="rounded-xl border border-border bg-card p-6 shadow-2xl shadow-primary/5 sm:p-8">
          <div className="mb-6">
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
              <Stethoscope size={18} />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Medical Staff Login</h1>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
              Sign in with your authorized NextCare staff account.
            </p>
          </div>

          <form className="space-y-4" onSubmit={submit}>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium">Email</span>
              <input
                type="email"
                name="email"
                autoComplete="username"
                required
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="input-alive h-10 w-full rounded-md border border-input bg-surface px-3 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-primary"
                placeholder="Admin"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium">Password</span>
              <div className="relative">
                <LockKeyhole
                  size={14}
                  className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground"
                />
                <input
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="input-alive h-10 w-full rounded-md border border-input bg-surface pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-primary"
                  placeholder="Enter your password"
                />
              </div>
            </label>

            {error ? (
              <div
                role="alert"
                className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-xs text-destructive"
              >
                {error}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading}
              className="pressable inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : (
                <ShieldCheck size={15} />
              )}
              {loading ? "Signing in…" : "Sign In"}
            </button>
          </form>

          <p className="mt-6 border-t border-border pt-4 text-center font-mono text-[10px] text-muted-foreground">
            Authorized medical personnel only
          </p>
        </section>
      </div>
    </main>
  );
}

function LoginSplash() {
  return (
    <main className="login-splash flex min-h-screen items-center justify-center bg-background px-4 py-10 text-foreground">
      <div className="login-splash-card w-full max-w-sm rounded-[2rem] border border-border/70 bg-card/95 p-8 text-center shadow-[0_30px_90px_-45px_rgba(39,35,49,0.25)] backdrop-blur-xl">
        <div className="relative mx-auto mb-7 flex h-28 w-28 items-center justify-center rounded-full bg-primary/10">
          <span className="login-splash-ring" />
          <img
            src="/favicon.ico"
            alt="NextCare loading"
            className="login-splash-logo relative h-20 w-20 rounded-3xl object-cover"
          />
        </div>
        <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">Preparing your console</p>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">NextCare</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Starting clinical decision support…
        </p>
      </div>
    </main>
  );
}

function StaffSessionCheck() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background text-muted-foreground">
      <div className="flex items-center gap-2 text-xs">
        <LoaderCircle size={15} className="animate-spin text-primary" />
        Verifying staff session…
      </div>
    </main>
  );
}
