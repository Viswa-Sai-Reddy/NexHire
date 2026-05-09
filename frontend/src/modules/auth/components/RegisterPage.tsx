import { type FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, XCircle } from "lucide-react";

import { useAuth } from "@/app/providers/AuthProvider";
import type { RegistrableRole } from "@/modules/auth/api";

const ROLE_OPTIONS: { value: RegistrableRole; label: string }[] = [
  { value: "REFERRER", label: "Referrer (Employee)" },
  { value: "MENTOR", label: "Mentor" },
  { value: "HR", label: "HR" },
  { value: "IT_AD", label: "IT / AD" },
  { value: "ADMIN", label: "Admin (Badge)" },
  { value: "PROGRAM_OWNER", label: "Program Owner" },
];

export function RegisterPage() {
  const { state, register } = useAuth();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<RegistrableRole>("REFERRER");

  const busy = state.status === "loading";
  const errorMessage = state.status === "error" ? state.message : null;

  if (state.status === "authenticated") {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (busy) return;
    await register({ email, full_name: fullName, password, role });
  };

  const fieldClass =
    "flex h-9 w-full rounded-md border border-white/20 bg-white/10 px-3 py-2 text-sm text-white shadow-sm transition-colors placeholder:text-white/50 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40";

  return (
    <div className="min-h-screen bg-hero-gradient text-foreground">
      <div className="container flex min-h-screen items-center justify-center py-12">
        <div className="w-full max-w-md rounded-xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-black/20 backdrop-blur">
          <Link
            to="/"
            className="inline-flex items-center gap-1 rounded text-sm text-white/70 outline-none transition-colors hover:text-white focus-visible:ring-2 focus-visible:ring-accent"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
            Back to sign in
          </Link>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">
            Create your account
          </h1>
          <p className="mt-1 text-sm text-white/70">
            Pick a role to provision your dashboard.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <label className="block space-y-1.5">
              <span className="block text-xs font-medium uppercase tracking-wide text-white/70">
                Full name
              </span>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                className={fieldClass}
                placeholder="Jane Doe"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="block text-xs font-medium uppercase tracking-wide text-white/70">
                Email
              </span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                className={fieldClass}
                placeholder="you@company.com"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="block text-xs font-medium uppercase tracking-wide text-white/70">
                Password
              </span>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                className={fieldClass}
                placeholder="At least 8 characters"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="block text-xs font-medium uppercase tracking-wide text-white/70">
                Role
              </span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as RegistrableRole)}
                className={fieldClass}
              >
                {ROLE_OPTIONS.map((opt) => (
                  <option
                    key={opt.value}
                    value={opt.value}
                    className="text-black"
                  >
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="submit"
              disabled={busy}
              className="flex h-9 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Creating account…" : "Create account"}
              {!busy && <ArrowRight className="h-4 w-4" aria-hidden />}
            </button>
            {errorMessage !== null && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/15 px-3 py-2 text-sm text-white"
              >
                <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                {errorMessage}
              </p>
            )}
          </form>

          <p className="mt-4 text-center text-sm text-white/70">
            Already have an account?{" "}
            <Link
              to="/"
              className="rounded font-medium text-accent underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
