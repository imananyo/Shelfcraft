"use client";
import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Card } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { LogoMark } from "./logo";

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

function SignIn() {
  const qc = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try { await post("/auth/login", { email, password }); qc.invalidateQueries(); }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="flex h-full items-center justify-center px-4">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-5 flex items-center gap-2"><LogoMark /><span className="font-display text-lg font-semibold">Shelfcraft</span></div>
        <h1 className="text-xl font-semibold">Sign in</h1>
        <p className="mb-4 text-[13px] text-muted">This workspace has team members enabled.</p>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="Email"><Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
          <Field label="Password"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          <Button type="submit" size="lg" loading={busy}>Sign in</Button>
        </form>
      </Card>
    </div>
  );
}
