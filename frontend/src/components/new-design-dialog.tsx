"use client";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { Field, Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const PRESETS = [
  { label: "Listing image", w: 2000, h: 2000 }, { label: "Square post", w: 1080, h: 1080 }, { label: "Portrait 4:5", w: 1080, h: 1350 },
  { label: "Story 9:16", w: 1080, h: 1920 }, { label: "Landscape 16:9", w: 1920, h: 1080 }, { label: "Sponsored Brand", w: 1200, h: 628 },
  { label: "A+ Premium banner", w: 1464, h: 600 }, { label: "A+ Basic banner", w: 970, h: 600 },
];
export function NewDesignDialog({ open, onOpenChange, onCreated, projectId }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (docId: string) => void; projectId?: string }) {
  const [name, setName] = React.useState("Untitled design");
  const [size, setSize] = React.useState({ w: 2000, h: 2000 });
  const [templateId, setTemplateId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const templates = useApi<{ id: string; name: string; category: string; width: number; height: number; thumb_url?: string }[]>(["templates"], open ? "/templates" : null);
  const create = async () => {
    setBusy(true);
    try {
      const r = await post<{ id: string }>("/documents", { name, project_id: projectId ?? null, width: size.w, height: size.h, template_id: templateId });
      onOpenChange(false);
      onCreated(r.id);
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  const importJson = async (files: File[]) => {
    try {
      const data = JSON.parse(await files[0].text());
      const r = await post<{ id: string }>("/documents/import", data);
      onOpenChange(false);
      onCreated(r.id);
    } catch (e) { toast.error(e instanceof SyntaxError ? "That file isn't valid JSON." : (e as Error).message); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New design" wide footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={create} loading={busy}>Create design</Button></>}>
      <div className="flex flex-col gap-5">
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <div>
          <div className="mb-2 text-[13px] font-medium">Blank canvas</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {PRESETS.map((p) => (
              <button key={p.label} onClick={() => { setSize({ w: p.w, h: p.h }); setTemplateId(null); }}
                className={cn("rounded-[10px] border px-3 py-2 text-left text-[12.5px]", !templateId && size.w === p.w && size.h === p.h ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                <div className="font-medium">{p.label}</div><div className="font-mono text-[11px] text-muted">{p.w}×{p.h}</div>
              </button>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:w-64">
            <Input type="number" value={size.w} onChange={(e) => { setSize({ ...size, w: Number(e.target.value) }); setTemplateId(null); }} aria-label="Custom width" />
            <Input type="number" value={size.h} onChange={(e) => { setSize({ ...size, h: Number(e.target.value) }); setTemplateId(null); }} aria-label="Custom height" />
          </div>
        </div>
        <div>
          <div className="mb-2 text-[13px] font-medium">Or start from a template</div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            {templates.data?.map((t) => (
              <button key={t.id} onClick={() => setTemplateId(t.id)} className={cn("overflow-hidden rounded-[10px] border text-left", templateId === t.id ? "border-primary ring-3 ring-[var(--ring)]" : "border-border")}>
                <TemplateThumb id={t.id} url={t.thumb_url} />
                <div className="truncate px-2 py-1.5 text-[11.5px] font-medium">{t.name}</div>
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted"><div className="h-px flex-1 bg-border" />or import<div className="h-px flex-1 bg-border" /></div>
        <Dropzone compact multiple={false} accept="application/json,.json" onFiles={importJson} label="Import a Shelfcraft project JSON" />
      </div>
    </Dialog>
  );
}

function TemplateThumb({ id, url }: { id: string; url?: string }) {
  const [src, setSrc] = React.useState(url);
  React.useEffect(() => { if (!src) post<{ thumb_url: string }>(`/templates/${id}/thumbnail`).then((r) => setSrc(r.thumb_url)).catch(() => undefined); }, [id, src]);
  // eslint-disable-next-line @next/next/no-img-element
  return src ? <img src={src} alt="" className="aspect-square w-full bg-sunken object-contain" /> : <Skeleton className="aspect-square rounded-none" />;
}

