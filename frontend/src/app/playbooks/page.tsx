"use client";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, Check, Clock, Copy, Download, MoreHorizontal, Plus, Search, Trash2, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { Confirm, Dialog, Menu, MenuItem } from "@/components/ui/overlay";
import { del, post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { CATEGORIES, estimateMinutes, formatMinutes, stepLabel, type PlaybookOptions, type PlaybookT } from "@/lib/playbooks";
import { cn, timeAgo } from "@/lib/utils";

function StepChips({ p, opts, max }: { p: PlaybookT; opts?: PlaybookOptions | null; max?: number }) {
  const shown = max ? p.steps.slice(0, max) : p.steps;
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((s, i) => <Badge key={i}>{stepLabel(s, opts)}</Badge>)}
      {max && p.steps.length > max && <Badge tone="primary">+{p.steps.length - max} more</Badge>}
    </div>
  );
}

export default function PlaybooksPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const mine = useApi<PlaybookT[]>(["playbooks"], "/playbooks");
  const lib = useApi<PlaybookT[]>(["playbooks", "templates"], "/playbooks?templates=true");
  const opts = useApi<PlaybookOptions>(["playbook-options"], "/playbooks/options");
  const [libOpen, setLibOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [cat, setCat] = React.useState("all");
  const [toDelete, setToDelete] = React.useState<PlaybookT | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);

  const copyOf = async (id: string, msg: string) => {
    setBusy(id);
    try {
      const p = await post<PlaybookT>(`/playbooks/${id}/import`);
      qc.invalidateQueries({ queryKey: ["playbooks"] });
      toast.success(msg);
      router.push(`/playbooks/${p.id}`);
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(null); }
  };
  const create = async () => {
    try {
      const p = await post<PlaybookT>("/playbooks", { name: "New playbook", steps: [{ kind: "creative", creative_type: "white_bg_main" }] });
      qc.invalidateQueries({ queryKey: ["playbooks"] });
      router.push(`/playbooks/${p.id}`);
    } catch (e) { toast.error((e as Error).message); }
  };

  const imported = new Set((mine.data ?? []).map((p) => p.name));
  const q = query.trim().toLowerCase();
  const list = (mine.data ?? []).filter((p) => (cat === "all" || p.category === cat)
    && (!q || p.name.toLowerCase().includes(q) || (p.description ?? "").toLowerCase().includes(q)));
  const cats = ["all", ...CATEGORIES.filter((c) => mine.data?.some((p) => p.category === c))];

  return (
    <>
      <PageHeader title="Playbooks" description="Reusable recipes: a sequence of generation steps you can run on any product, or on many at once."
        actions={<><Button variant="outline" onClick={() => setLibOpen(true)}><BookOpen />Playbook templates</Button><Button onClick={create}><Plus />New playbook</Button></>} />
      {mine.error ? <ErrorState error={mine.error} onRetry={() => mine.refetch()} /> : mine.isLoading ? <Skeleton className="h-40" /> : !mine.data?.length ? (
        <EmptyState icon={<Workflow />} title="No playbooks yet" body="Start from a playbook template or create from scratch."
          action={<div className="flex gap-2"><Button variant="outline" onClick={() => setLibOpen(true)}>Playbook templates</Button><Button onClick={create}>New playbook</Button></div>} />
      ) : (
        <>
          {mine.data.length > 3 && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <div className="relative w-full sm:w-64">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
                <Input className="pl-8" placeholder="Search playbooks" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search playbooks" />
              </div>
              {cats.length > 2 && cats.map((c) => (
                <button key={c} onClick={() => setCat(c)} className={cn("rounded-full border px-3 py-1 text-[12.5px] capitalize",
                  cat === c ? "border-primary bg-primary-soft text-primary" : "border-border text-muted hover:bg-sunken")}>{c}</button>
              ))}
            </div>
          )}
          {!list.length ? <p className="py-10 text-center text-[13px] text-muted">No playbooks match.</p> : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {list.map((p) => (
                <Card key={p.id} className="relative flex h-full flex-col p-4 transition hover:border-border-strong">
                  <div className="flex items-start justify-between gap-2">
                    <Link href={`/playbooks/${p.id}`} className="text-[15px] font-semibold after:absolute after:inset-0 after:content-['']">{p.name}</Link>
                    <div className="relative z-10 flex items-center gap-1">
                      <Badge className="capitalize">{p.category}</Badge>
                      <Menu trigger={<Button size="icon-sm" variant="ghost" aria-label={`More actions for ${p.name}`}><MoreHorizontal /></Button>}>
                        <MenuItem icon={<Copy />} onSelect={() => copyOf(p.id, "Duplicated")} disabled={busy === p.id}>Duplicate</MenuItem>
                        <MenuItem icon={<Trash2 />} destructive onSelect={() => setToDelete(p)}>Delete</MenuItem>
                      </Menu>
                    </div>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[12.5px] text-muted">{p.description || "No description"}</p>
                  <div className="mt-3 flex-1"><StepChips p={p} opts={opts.data} max={6} /></div>
                  <div className="mt-3 flex items-center gap-3 text-[11px] text-muted">
                    <span>{p.steps.length} step{p.steps.length === 1 ? "" : "s"}</span>
                    <span className="flex items-center gap-1"><Clock className="size-3" />{formatMinutes(p.estimate_minutes ?? estimateMinutes(p.steps))} per product</span>
                    <span className="ml-auto">updated {timeAgo(p.updated_at)}</span>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
      <Dialog open={libOpen} onOpenChange={setLibOpen} title="Playbook templates" wide description="Import a template to make your own editable copy. Times are rough CPU estimates per product.">
        {lib.isLoading ? <Skeleton className="h-40" /> : (
          <div className="grid gap-3 sm:grid-cols-2">
            {lib.data?.map((t) => (
              <Card key={t.id} className="flex flex-col p-4">
                <div className="flex items-center justify-between"><h3 className="text-[14px] font-semibold">{t.name}</h3><Badge className="capitalize">{t.category}</Badge></div>
                <p className="mt-1 flex-1 text-[12.5px] text-muted">{t.description}</p>
                <div className="mt-2"><StepChips p={t} opts={opts.data} /></div>
                <div className="mt-3 flex items-center gap-3">
                  <Button size="sm" onClick={() => copyOf(t.id, "Imported — customize and run it")} loading={busy === t.id}><Download />Import</Button>
                  <span className="flex items-center gap-1 text-[11px] text-muted"><Clock className="size-3" />{formatMinutes(t.estimate_minutes ?? estimateMinutes(t.steps))}</span>
                  {imported.has(t.name) && <span className="ml-auto flex items-center gap-1 text-[11px] text-success"><Check className="size-3" />In your playbooks</span>}
                </div>
              </Card>
            ))}
          </div>
        )}
      </Dialog>
      <Confirm open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title={`Delete “${toDelete?.name ?? ""}”?`}
        body="Past runs and everything they generated are kept."
        onConfirm={async () => {
          if (!toDelete) return;
          try { await del(`/playbooks/${toDelete.id}`); qc.invalidateQueries({ queryKey: ["playbooks"] }); toast.success("Playbook deleted"); }
          catch (e) { toast.error((e as Error).message); } finally { setToDelete(null); }
        }} />
    </>
  );
}
