"use client";
import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { AuthAlert, AuthButton, AuthField, AuthInput, AuthLayout, PasswordInput } from "./auth-layout";

export interface AuthStatus { team_mode: boolean; signed_in: boolean; member: { id: string; name: string; email: string; role: string } | null }

export function useAuth() {
  return useApi<AuthStatus>(["auth"], "/auth/status", { refetchInterval: 60_000 });
}

/** In team mode, requires sign-in before showing the app. Single-user mode passes straight through. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const q = useAuth();
  if (q.isLoading) return <div className="flex h-full items-center justify-center"><div className="size-8 animate-pulse rounded-[9px] bg-primary/80" /></div>;
  if (q.data?.team_mode && !q.data.signed_in) return <SignIn />;
  return <>{children}</>;
}

const EMAIL_KEY = "shelfcraft.lastEmail";
const readEmail = () => { try { return localStorage.getItem(EMAIL_KEY) ?? ""; } catch { return ""; } };

function SignIn() {
  const qc = useQueryClient();
  const [email, setEmail] = React.useState(readEmail);
  const [password, setPassword] = React.useState("");
  const [remember, setRemember] = React.useState(() => !!readEmail());
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [caps, setCaps] = React.useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await post("/auth/login", { email: email.trim(), password });
      try { if (remember) localStorage.setItem(EMAIL_KEY, email.trim()); else localStorage.removeItem(EMAIL_KEY); } catch { /* storage blocked */ }
      qc.invalidateQueries();
    } catch (err) {
      const msg = (err as Error).message;
      setError(/wrong email or password/i.test(msg) ? "That email and password don't match. Check both and try again." : msg || "Couldn't sign in. Is Shelfcraft running?");
      setPassword("");
    } finally { setBusy(false); }
  };
  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to your team's Shelfcraft workspace."
      footer={<>Forgot your password? Ask the workspace owner to reset it in <span className="font-medium text-[#4a4a4a] dark:text-[#ccc]">Settings → Team</span>.</>}>
      {error && <AuthAlert>{error}</AuthAlert>}
      <form onSubmit={submit} className="flex flex-col gap-5" noValidate={false}>
        <AuthField label="Work email">
          <AuthInput type="email" autoComplete="username" placeholder="you@company.com" value={email} required autoFocus={!email}
            aria-invalid={!!error || undefined} onChange={(e) => { setEmail(e.target.value); setError(null); }} />
        </AuthField>
        <AuthField label="Password" error={caps ? "Caps Lock is on" : undefined}>
          <PasswordInput autoComplete="current-password" value={password} invalid={!!error} onCaps={setCaps}
            onChange={(v) => { setPassword(v); setError(null); }} />
        </AuthField>
        <label className="flex cursor-pointer select-none items-center gap-2.5 text-[13px] font-light text-[#4a4a4a] dark:text-[#bbb]">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="size-4 accent-[#0a0a0a] dark:accent-white" />
          Remember my email on this device
        </label>
        <AuthButton type="submit" loading={busy}>{busy ? "Signing in…" : "Sign in"}</AuthButton>
      </form>
    </AuthLayout>
  );
}
