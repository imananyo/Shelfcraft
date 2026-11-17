"use client";
import { Copy, Link2, Share2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Notice } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { del, get, post } from "@/lib/api";

type Share = { enabled: boolean; url: string | null };

/** "Share" — creates a no-login, read-only gallery link for one project's visuals. */
export function ShareButton({ projectId }: { projectId: string }) {
  const [open, setOpen] = React.useState(false);
  const [s, setS] = React.useState<Share | null>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (open) get<Share>(`/projects/${projectId}/share`).then(setS).catch(() => setS(null)); }, [open, projectId]);
  const full = s?.url ? `${window.location.origin}${s.url}` : "";
  const run = async (fn: () => Promise<Share>) => { setBusy(true); try { setS(await fn()); } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); } };
  const copy = async () => { try { await navigator.clipboard.writeText(full); toast.success("Link copied"); } catch { toast.error("Couldn't copy — select the link and copy it manually"); } };
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}><Share2 />Share</Button>
      <Dialog open={open} onOpenChange={setOpen} title="Share link" description="Anyone with the link can view these visuals — no sign-in needed. They can't edit anything.">
        <div className="flex flex-col gap-3">
          {s?.enabled ? (
            <>
              <div className="flex gap-2"><Input readOnly value={full} onFocus={(e) => e.currentTarget.select()} /><Button onClick={copy}><Copy />Copy</Button></div>
              <Notice className="text-[12.5px]">The link works for people who can reach this computer (e.g. on your Wi-Fi with <code>start.ps1 -Lan</code>).</Notice>
              <div className="flex justify-between">
                <a href={s.url!} target="_blank" rel="noreferrer" className="text-[13px] text-primary underline">Open gallery</a>
                <Button variant="ghost" loading={busy} onClick={() => run(() => del(`/projects/${projectId}/share`).then(() => ({ enabled: false, url: null })))}>Revoke link</Button>
              </div>
            </>
          ) : (
            <Button loading={busy} onClick={() => run(() => post<Share>(`/projects/${projectId}/share`))}><Link2 />Create share link</Button>
          )}
        </div>
      </Dialog>
    </>
  );
}
