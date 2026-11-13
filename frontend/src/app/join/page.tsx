"use client";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { LogoMark } from "@/components/shell/logo";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Card } from "@/components/ui/misc";
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
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-5 flex items-center gap-2"><LogoMark /><span className="font-display text-lg font-semibold">Shelfcraft</span></div>
        <h1 className="text-xl font-semibold">Join the workspace</h1>
        <p className="mb-4 text-[13px] text-muted">Choose your name and a password to accept the invite.</p>
        {!token ? <p className="text-[13px] text-danger">This invite link is missing its token.</p> : (
          <form onSubmit={submit} className="flex flex-col gap-3">
            <Field label="Your name"><Input value={name} onChange={(e) => setName(e.target.value)} required /></Field>
            <Field label="Password" hint="At least 8 characters"><Input type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} required /></Field>
            <Button type="submit" size="lg" loading={busy}>Accept invite</Button>
          </form>
        )}
      </Card>
    </div>
  );
}

export default function Page() {
  return <React.Suspense><Join /></React.Suspense>;
}
