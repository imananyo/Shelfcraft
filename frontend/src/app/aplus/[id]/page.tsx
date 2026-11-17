"use client";
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useQueryClient } from "@tanstack/react-query";
import { Download, Eye, GripVertical, PenLine, Plus, RefreshCw, Trash2, Smartphone } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { ShareButton } from "@/components/share-button";
import { toast } from "sonner";
import { ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Badge, Card, ErrorState, Notice, PageHeader, Skeleton } from "@/components/ui/misc";
import { Confirm, Dialog, Menu, MenuItem } from "@/components/ui/overlay";
import { del, download, post, put } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { DocSummary } from "@/lib/types";

interface Module { type: string; document_id: string; label: string; document: DocSummary }
interface Aplus { id: string; name: string; tier: string; modules: Module[]; note: string; product_id?: string }

function Row({ m, index, onRemove }: { m: Module; index: number; onRemove: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: m.document_id });
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={isDragging ? "z-10 opacity-80" : ""}>
      <Card className="flex items-center gap-4 p-3">
        <button {...attributes} {...listeners} aria-label="Drag to reorder" className="cursor-grab touch-none text-muted hover:text-foreground"><GripVertical className="size-5" /></button>
        <span className="w-6 text-center font-mono text-xs text-muted">{index + 1}</span>
        <ImageThumb src={m.document.thumb_url} alt={m.label} className="h-20 w-48 shrink-0 [&_img]:object-contain" />
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] font-medium">{m.label}</div>
          <div className="font-mono text-[11px] text-muted">{m.document.width}×{m.document.height}</div>
        </div>
        <Link href={`/editor/${m.document_id}`}><Button size="sm" variant="outline"><PenLine />Edit</Button></Link>
        <Button size="icon-sm" variant="ghost" aria-label="Remove module" onClick={onRemove}><Trash2 /></Button>
      </Card>
    </div>
  );
}

export default function AplusPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useApi<Aplus>(["aplus", id], `/aplus/${id}`);
  const lib = useApi<{ modules: Record<string, { label: string }> }>(["aplus-modules"], "/aplus/modules");
  const [order, setOrder] = React.useState<Module[]>([]);
  const [preview, setPreview] = React.useState<string | null>(null);
  const [confirm, setConfirm] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));
  React.useEffect(() => { if (q.data) setOrder(q.data.modules); }, [q.data]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["aplus", id] });

  // Ensure every module has a thumbnail (rendered server-side on first view).
  React.useEffect(() => {
    q.data?.modules.filter((m) => !m.document.thumb_url).forEach((m) =>
      fetch(`/api/documents/${m.document_id}`).then((r) => r.json()).then((d) =>
        put(`/documents/${m.document_id}`, { document: d.document, base_version: d.version, thumbnail: true }).then(refresh).catch(() => undefined)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data?.modules.length]);

  const onDragEnd = async (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const from = order.findIndex((m) => m.document_id === e.active.id), to = order.findIndex((m) => m.document_id === e.over!.id);
    const next = arrayMove(order, from, to);
    setOrder(next);
    try { await put(`/aplus/${id}/order`, { document_ids: next.map((m) => m.document_id) }); refresh(); } catch (er) { toast.error((er as Error).message); }
  };

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-96" />;
  return (
    <>
      <PageHeader eyebrow={<Link href="/aplus" className="hover:text-foreground">A+ content</Link>} title={q.data.name} description={<span className="flex items-center gap-2"><Badge className="capitalize">{q.data.tier}</Badge>{order.length} modules · drag to reorder</span>}
        actions={<>
          <ShareButton projectId={id} />
          <Button variant="outline" onClick={() => setPreview(`/api/aplus/${id}/preview.png?t=${Date.now()}`)} disabled={!order.length}><Eye />Preview</Button>
          {q.data.tier !== "mobile" && <Button variant="outline" disabled={!order.length} onClick={async () => { try { const m = await post<{ id: string }>(`/aplus/${id}/convert-mobile`); toast.success("Mobile version created — your edits were carried over"); router.push(`/aplus/${m.id}`); } catch (e) { toast.error((e as Error).message); } }}><Smartphone />Make mobile version</Button>}
          <Button variant="outline" loading={busy} disabled={!order.length} onClick={async () => { setBusy(true); try { await download(`/aplus/${id}/export.zip`, { method: "POST" }); } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); } }}><Download />Export ZIP</Button>
          <Menu trigger={<Button disabled={order.length >= 7}><Plus />Add module</Button>}>
            {lib.data && Object.entries(lib.data.modules).map(([k, m]) => <MenuItem key={k} onSelect={async () => { await post(`/aplus/${id}/modules`, { type: k }); refresh(); toast.success(`${m.label} added`); }}>{m.label}</MenuItem>)}
          </Menu>
          <Button variant="ghost" size="icon" aria-label="Delete layout" onClick={() => setConfirm(true)}><Trash2 /></Button>
        </>} />
      <div className="flex flex-col gap-3">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={order.map((m) => m.document_id)} strategy={verticalListSortingStrategy}>
            {order.map((m, i) => <Row key={m.document_id} m={m} index={i} onRemove={async () => { try { await del(`/aplus/${id}/modules/${m.document_id}`); refresh(); } catch (e) { toast.error((e as Error).message); } }} />)}
          </SortableContext>
        </DndContext>
        <Notice className="text-xs"><RefreshCw className="mr-1 inline size-3" />Thumbnails refresh when you save in the editor. {q.data.note}</Notice>
      </div>
      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)} title="Preview" description="All modules stacked as they'd appear on a product page." wide>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {preview && <img src={preview} alt="A+ preview" className="w-full rounded-[10px] border border-border" />}
      </Dialog>
      <Confirm open={confirm} onOpenChange={setConfirm} title="Delete this A+ layout?" onConfirm={async () => { await del(`/aplus/${id}`); qc.invalidateQueries({ queryKey: ["aplus"] }); router.push("/aplus"); }} />
    </>
  );
}
