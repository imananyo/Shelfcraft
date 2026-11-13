"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Download, PenLine, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { Confirm } from "@/components/ui/overlay";
import { del, download } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { DocSummary } from "@/lib/types";
import { timeAgo } from "@/lib/utils";
import { NewDesignDialog } from "@/components/new-design-dialog";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useApi<{ id: string; name: string; kind: string; documents: DocSummary[]; updated_at: string }>(["project", id], `/projects/${id}`);
  const [newOpen, setNewOpen] = React.useState(false);
  const [doomed, setDoomed] = React.useState<DocSummary | null>(null);
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  return (
    <>
      <PageHeader eyebrow={<Link href="/projects" className="hover:text-foreground">Designs</Link>} title={p?.name ?? "…"} description={p ? `${p.documents.length} design(s) · updated ${timeAgo(p.updated_at)}` : undefined}
        actions={<>
          <Button variant="outline" disabled={!p?.documents.length} onClick={() => download(`/projects/${id}/export.zip`, { method: "POST" }).catch((e) => toast.error(e.message))}><Download />Export all (ZIP)</Button>
          <Button onClick={() => setNewOpen(true)}><Plus />Add design</Button>
        </>} />
      {!p ? <Skeleton className="h-64" /> : p.documents.length === 0 ? (
        <EmptyState icon={<PenLine />} title="No designs in this project" body="Add a blank canvas or start from a template." action={<Button onClick={() => setNewOpen(true)}><Plus />Add design</Button>} />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {p.documents.map((d) => (
            <Card key={d.id} className="overflow-hidden">
              <Link href={`/editor/${d.id}`}><ImageThumb src={d.thumb_url} alt={d.name} className="checkerboard aspect-[4/3] rounded-none border-0 [&_img]:object-contain" /></Link>
              <div className="flex items-center gap-2 p-3">
                <Link href={`/editor/${d.id}`} className="min-w-0 flex-1"><div className="truncate text-[13px] font-medium">{d.name}</div><div className="font-mono text-[11px] text-muted">{d.width}×{d.height} · v{d.version}</div></Link>
                <button aria-label="Delete design" className="text-muted hover:text-danger" onClick={() => setDoomed(d)}><Trash2 className="size-4" /></button>
              </div>
            </Card>
          ))}
        </div>
      )}
      <NewDesignDialog open={newOpen} onOpenChange={setNewOpen} projectId={id} onCreated={(docId) => router.push(`/editor/${docId}`)} />
      <Confirm open={!!doomed} onOpenChange={(o) => !o && setDoomed(null)} title={`Delete “${doomed?.name}”?`}
        onConfirm={async () => { await del(`/documents/${doomed!.id}`); setDoomed(null); qc.invalidateQueries({ queryKey: ["project", id] }); }} />
    </>
  );
}
