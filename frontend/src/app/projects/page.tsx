"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Copy, MoreHorizontal, PenLine, Plus, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { NewDesignDialog } from "@/components/new-design-dialog";
import { Confirm, Menu, MenuItem, MenuSeparator } from "@/components/ui/overlay";
import { del, post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn, timeAgo } from "@/lib/utils";

interface ProjectRow { id: string; name: string; kind: string; thumb_url?: string; document_count: number; updated_at: string }
const KIND_HREF = (p: ProjectRow) => ({ listing: `/listings/${p.id}`, aplus: `/aplus/${p.id}`, video: `/videos/${p.id}` } as Record<string, string>)[p.kind] ?? `/projects/${p.id}`;


function Projects() {
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const [q, setQ] = React.useState("");
  const [kind, setKind] = React.useState("");
  const [newOpen, setNewOpen] = React.useState(sp.get("new") === "1");
  const [doomed, setDoomed] = React.useState<ProjectRow | null>(null);
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  const list = useApi<ProjectRow[]>(["projects", params.toString()], `/projects?${params}`);
  return (
    <>
      <PageHeader title="Designs & projects" description="Every generated creative is saved as a layered design you can reopen and keep editing."
        actions={<Button onClick={() => setNewOpen(true)}><Plus />New design</Button>} />
      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative min-w-56 flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search projects…" /></div>
        <div className="flex rounded-[10px] border border-border-strong p-0.5 text-[12.5px]">
          {[["", "All"], ["design", "Designs"], ["listing", "Listings"], ["aplus", "A+"], ["video", "Videos"]].map(([k, l]) => (
            <button key={k} onClick={() => setKind(k)} className={cn("rounded-[8px] px-3 py-1.5", kind === k ? "bg-sunken font-medium" : "text-muted")}>{l}</button>
          ))}
        </div>
      </div>
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.isLoading ? <div className="grid grid-cols-2 gap-4 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-56" />)}</div>
        : !list.data?.length ? <EmptyState icon={<PenLine />} title="No projects yet" body="Start from a blank canvas or a template, or generate creatives — they'll show up here." action={<Button onClick={() => setNewOpen(true)}><Plus />New design</Button>} />
        : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {list.data.map((p) => (
              <Card key={p.id} className="group overflow-hidden">
                <Link href={KIND_HREF(p)}><ImageThumb src={p.thumb_url} alt={p.name} className="aspect-[4/3] rounded-none border-0 [&_img]:object-contain" /></Link>
                <div className="flex items-start gap-2 p-3">
                  <Link href={KIND_HREF(p)} className="min-w-0 flex-1"><div className="truncate text-[13.5px] font-medium">{p.name}</div><div className="text-xs text-muted">{timeAgo(p.updated_at)}{p.kind === "design" ? ` · ${p.document_count} design${p.document_count === 1 ? "" : "s"}` : ""}</div></Link>
                  <Badge className="capitalize">{p.kind}</Badge>
                  <Menu trigger={<button aria-label="Project actions" className="text-muted hover:text-foreground"><MoreHorizontal className="size-4" /></button>}>
                    <MenuItem icon={<Copy />} onSelect={async () => { await post(`/projects/${p.id}/duplicate`); qc.invalidateQueries({ queryKey: ["projects"] }); toast.success("Duplicated"); }}>Duplicate</MenuItem>
                    <MenuSeparator />
                    <MenuItem icon={<Trash2 />} destructive onSelect={() => setDoomed(p)}>Delete</MenuItem>
                  </Menu>
                </div>
              </Card>
            ))}
          </div>
        )}
      <NewDesignDialog open={newOpen} onOpenChange={setNewOpen} onCreated={(docId) => router.push(`/editor/${docId}`)} />
      <Confirm open={!!doomed} onOpenChange={(o) => !o && setDoomed(null)} title={`Delete “${doomed?.name}”?`} body="Generated images stay in your asset library."
        onConfirm={async () => { await del(`/projects/${doomed!.id}`); setDoomed(null); qc.invalidateQueries({ queryKey: ["projects"] }); toast.success("Project deleted"); }} />
    </>
  );
}

export default function Page() {
  return <React.Suspense><Projects /></React.Suspense>;
}
