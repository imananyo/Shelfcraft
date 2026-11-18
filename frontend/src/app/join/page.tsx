"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { AuthAlert, AuthButton, AuthField, AuthInput, AuthLayout, PasswordInput } from "@/components/shell/auth-layout";
import { post } from "@/lib/api";

function Join() {
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = React.useState("");
  const [pw, setPw] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const token = sp.get("token") ?? "";
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pw.length < 8) return toast.error("Use at least 8 characters.");
    setBusy(true);
    try { await post("/auth/accept-invite", { token, name, password: pw }); qc.invalidateQueries(); toast.success("Welcome to the team!"); router.replace("/"); }
    catch (err) { toast.error((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <AuthLayout title="Join the workspace" subtitle="You've been invited. Choose your name and a password to get started."
      footer="Already have an account? Open Shelfcraft and sign in.">
      {!token ? <AuthAlert>This invite link is missing its token. Ask for a new invite link.</AuthAlert> : (
        <form onSubmit={submit} className="flex flex-col gap-5">
          <AuthField label="Your name"><AuthInput autoComplete="name" placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></AuthField>
          <AuthField label="Password" hint={pw && pw.length < 8 ? `${8 - pw.length} more character${8 - pw.length === 1 ? "" : "s"} needed` : "At least 8 characters"}>
            <PasswordInput autoComplete="new-password" value={pw} onChange={setPw} />
          </AuthField>
          <AuthButton type="submit" loading={busy}>Accept invite</AuthButton>
        </form>
      )}
    </AuthLayout>
  );
}

export default function Page() {
  return <React.Suspense><Join /></React.Suspense>;
}
