"use client";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Check, Cloud, CloudOff, Download, FileJson, Grid3x3, History, LayoutTemplate, LoaderCircle, Magnet, PanelLeft, PanelRight,
  Redo2, Save, TriangleAlert, Undo2, ZoomIn, ZoomOut,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { stageHandle } from "@/components/editor/canvas";
import { LayersPanel, PropertiesPanel, ToolRail, useEditorShortcuts } from "@/components/editor/panels";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Badge, ErrorState, Skeleton } from "@/components/ui/misc";
import { Dialog, Menu, MenuItem, MenuLabel, MenuSeparator, Tip } from "@/components/ui/overlay";
import { ApiError, download, get, post, put, upload } from "@/lib/api";
import { useEditor } from "@/lib/editor-store";
import { useActiveBrand } from "@/lib/hooks";
import type { DocSummary, EditorDoc } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

const EditorCanvas = dynamic(() => import("@/components/editor/canvas").then((m) => m.EditorCanvas), { ssr: false, loading: () => <Skeleton className="m-8 h-[70vh]" /> });

type SaveState = "saved" | "saving" | "dirty" | "error" | "conflict";

export default function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { brand } = useActiveBrand();
  const st = useEditor();
  const [meta, setMeta] = React.useState<DocSummary | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [saveState, setSaveState] = React.useState<SaveState>("saved");
  const [name, setName] = React.useState("");
  const [panels, setPanels] = React.useState(() => ({ left: true, right: typeof window === "undefined" || window.innerWidth >= 1024 }));
  const [templatesOpen, setTemplatesOpen] = React.useState(false);
  const [revisionsOpen, setRevisionsOpen] = React.useState(false);
  const [saveTemplateOpen, setSaveTemplateOpen] = React.useState(false);
  const version = React.useRef(0);
  const lastCheckpoint = React.useRef(0); // set on first save; 0 = "no checkpoint yet"
  const saving = React.useRef(false);
  const backupKey = `shelfcraft-doc-backup-${id}`;

  useEditorShortcuts(!!st.doc);

  // Load (and offer recovery of an unsaved local backup).
  React.useEffect(() => {
    let alive = true;
    get<DocSummary & { document: EditorDoc }>(`/documents/${id}`).then((r) => {
      if (!alive) return;
      version.current = r.version;
      setMeta(r);
      setName(r.name);
      let doc = r.document;
      try {
        const raw = localStorage.getItem(backupKey);
        if (raw) {
          const b = JSON.parse(raw) as { version: number; doc: EditorDoc; at: number };
          if (b.version === r.version && JSON.stringify(b.doc) !== JSON.stringify(r.document)) {
            doc = b.doc;
            toast.message("Recovered unsaved changes from your last session", { description: `From ${new Date(b.at).toLocaleTimeString()}. They'll be saved now.` });
            setTimeout(() => useEditor.setState((s) => ({ dirtyCounter: s.dirtyCounter + 1 })), 50);
          } else localStorage.removeItem(backupKey);
        }
      } catch { /* storage unavailable */ }
      useEditor.getState().load(doc);
    }).catch((e) => setError(e));
    return () => { alive = false; useEditor.getState().load(null); };
  }, [id, backupKey]);

  const save = React.useCallback(async (opts: { checkpoint?: boolean; thumbnail?: boolean; silent?: boolean } = {}) => {
    const doc = useEditor.getState().doc;
    if (!doc || saving.current) return;
    saving.current = true;
    setSaveState("saving");
    const checkpoint = opts.checkpoint || Date.now() - lastCheckpoint.current > 5 * 60_000;
    try {
      const r = await put<DocSummary>(`/documents/${id}`, { document: doc, base_version: version.current, name: name || undefined, checkpoint, thumbnail: !!opts.thumbnail });
      version.current = r.version;
      if (checkpoint) lastCheckpoint.current = Date.now();
      setMeta(r);
      setSaveState(useEditor.getState().doc === doc ? "saved" : "dirty");
      try { localStorage.removeItem(backupKey); } catch { /* ignore */ }
      if (!opts.silent && opts.thumbnail) toast.success("Saved");
      qc.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      const err = e as ApiError;
      setSaveState(err.status === 409 ? "conflict" : "error");
      if (err.status === 409) toast.error("This design was changed in another tab. Reload to get the latest version — your changes are backed up locally.");
      else if (!opts.silent) toast.error(`Couldn't save: ${err.message}. Your changes are kept locally and will retry.`);
    } finally { saving.current = false; }
  }, [id, name, backupKey, qc]);

  // Autosave: local backup immediately, server save debounced.
  React.useEffect(() => {
    if (!st.doc || st.dirtyCounter === 0) return;
    setSaveState((s) => (s === "conflict" ? s : "dirty"));
    try { localStorage.setItem(backupKey, JSON.stringify({ version: version.current, doc: st.doc, at: Date.now() })); } catch { /* quota */ }
    const t = setTimeout(() => { if (saveState !== "conflict") save({ silent: true }); }, 1500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [st.dirtyCounter]);

  // Retry failed saves every 10 s; warn before closing with unsaved work.
  React.useEffect(() => {
    if (saveState !== "error") return;
    const t = setInterval(() => save({ silent: true }), 10_000);
    return () => clearInterval(t);
  }, [saveState, save]);
  React.useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (saveState === "dirty" || saveState === "saving" || saveState === "error") e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [saveState]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save({ checkpoint: true, thumbnail: true }); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  const exportClient = async (fmt: "png" | "jpeg", toLibrary = false) => {
    const url = stageHandle.exportDataURL?.(`image/${fmt}`, 0.92);
    if (!url) return toast.error("Canvas not ready yet");
    const blob = await (await fetch(url)).blob();
    const fname = `${(name || "design").replace(/[^\w\- ]+/g, "_")}.${fmt === "jpeg" ? "jpg" : "png"}`;
    if (toLibrary) {
      try { await upload("/assets", new File([blob], fname, { type: blob.type }), "files"); toast.success("Saved to asset library"); qc.invalidateQueries({ queryKey: ["assets"] }); }
      catch (e) { toast.error((e as Error).message); }
      return;
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    const d = useEditor.getState().doc!;
    toast.success(`Exported ${d.width}×${d.height} ${fmt.toUpperCase()} · ${(blob.size / 1024).toFixed(0)} KB`);
  };

  if (error) return <div className="p-8"><ErrorState error={error} /></div>;
  const doc = st.doc;
  const statusIcon = { saved: <Check className="size-3.5 text-success" />, saving: <LoaderCircle className="size-3.5 animate-spin" />, dirty: <Cloud className="size-3.5" />, error: <CloudOff className="size-3.5 text-danger" />, conflict: <TriangleAlert className="size-3.5 text-danger" /> }[saveState];
  const statusText = { saved: meta ? `Saved ${timeAgo(meta.updated_at)}` : "Saved", saving: "Saving…", dirty: "Unsaved changes", error: "Offline — retrying", conflict: "Conflict — reload" }[saveState];

  return (
    <div className="flex h-full flex-col">
      <div className="scrollbar-thin flex h-12 shrink-0 items-center gap-1.5 overflow-x-auto border-b border-border bg-surface px-2">
        <Link href={meta?.project_id ? `/projects/${meta.project_id}` : "/projects"}><Button variant="ghost" size="icon-sm" aria-label="Back"><ArrowLeft /></Button></Link>
        <input value={name} onChange={(e) => setName(e.target.value)} onBlur={() => save({ silent: true })} aria-label="Design name"
          className="h-8 w-44 rounded-[8px] border border-transparent bg-transparent px-2 text-[13.5px] font-medium hover:border-border focus:border-primary focus:outline-none sm:w-64" />
        <span className="hidden shrink-0 items-center gap-1.5 whitespace-nowrap text-xs text-muted md:flex">{statusIcon}{statusText}</span>
        <div className="mx-2 h-5 w-px bg-border" />
        <Tip content="Undo (Ctrl+Z)"><Button variant="ghost" size="icon-sm" aria-label="Undo" disabled={!st.past.length} onClick={st.undo}><Undo2 /></Button></Tip>
        <Tip content="Redo (Ctrl+Y)"><Button variant="ghost" size="icon-sm" aria-label="Redo" disabled={!st.future.length} onClick={st.redo}><Redo2 /></Button></Tip>
        <div className="mx-1 h-5 w-px bg-border" />
        <Tip content="Zoom out"><Button variant="ghost" size="icon-sm" aria-label="Zoom out" onClick={() => st.setZoom(st.zoom / 1.2)}><ZoomOut /></Button></Tip>
        <button className="w-12 text-center text-xs tabular-nums text-muted hover:text-foreground" onClick={() => st.setZoom(1)} title="Reset to 100%">{Math.round(st.zoom * 100)}%</button>
        <Tip content="Zoom in"><Button variant="ghost" size="icon-sm" aria-label="Zoom in" onClick={() => st.setZoom(st.zoom * 1.2)}><ZoomIn /></Button></Tip>
        <Tip content="Grid"><Button variant="ghost" size="icon-sm" aria-label="Toggle grid" className={cn(st.showGrid && "bg-ai-soft text-ai")} onClick={st.toggleGrid}><Grid3x3 /></Button></Tip>
        <Tip content="Snap to guides"><Button variant="ghost" size="icon-sm" aria-label="Toggle snapping" className={cn(st.snap && "bg-ai-soft text-ai")} onClick={st.toggleSnap}><Magnet /></Button></Tip>
        {doc && <Badge className="ml-1 hidden font-mono lg:inline-flex">{doc.width}×{doc.height}</Badge>}
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <Tip content="Layers panel"><Button variant="ghost" size="icon-sm" aria-label="Toggle layers panel" onClick={() => setPanels((p) => ({ ...p, left: !p.left }))}><PanelLeft /></Button></Tip>
          <Tip content="Properties panel"><Button variant="ghost" size="icon-sm" aria-label="Toggle properties panel" onClick={() => setPanels((p) => ({ ...p, right: !p.right }))}><PanelRight /></Button></Tip>
          <Button variant="ghost" size="sm" onClick={() => setRevisionsOpen(true)}><History /><span className="hidden sm:inline">History</span></Button>
          <Menu trigger={<Button variant="outline" size="sm"><Download />Export</Button>}>
            <MenuLabel>Download</MenuLabel>
            <MenuItem onSelect={() => exportClient("png")}>PNG · native size</MenuItem>
            <MenuItem onSelect={() => exportClient("jpeg")}>JPEG · native size</MenuItem>
            <MenuItem onSelect={() => download(`/documents/${id}/export?format=webp`).catch((e) => toast.error(e.message))}>WebP (server render)</MenuItem>
            <MenuSeparator />
            <MenuItem onSelect={() => exportClient("png", true)}>Save PNG to library</MenuItem>
            <MenuItem icon={<LayoutTemplate />} onSelect={() => setSaveTemplateOpen(true)}>Save as template</MenuItem>
            <MenuItem icon={<FileJson />} onSelect={async () => { await save({ silent: true }); download(`/documents/${id}/export?format=json`); }}>Project JSON</MenuItem>
          </Menu>
          <Button size="sm" onClick={() => save({ checkpoint: true, thumbnail: true })} loading={saveState === "saving"}><Save />Save</Button>
        </div>
      </div>
      {saveState === "conflict" && (
        <div className="flex items-center gap-3 bg-danger-soft px-4 py-2 text-[13px]">
          <TriangleAlert className="size-4 text-danger" />This design was saved from another tab or window. Your edits are backed up in this browser.
          <Button size="sm" variant="outline" onClick={() => { try { localStorage.removeItem(backupKey); } catch { /* ignore */ } location.reload(); }}>Discard mine & reload</Button>
          <Button size="sm" onClick={async () => { const r = await get<DocSummary>(`/documents/${id}`); version.current = r.version; setSaveState("dirty"); save({ checkpoint: true }); }}>Keep mine (overwrite)</Button>
        </div>
      )}
      <div className="relative flex min-h-0 flex-1">
        {doc && <ToolRail onTemplates={() => setTemplatesOpen(true)} />}
        {panels.left && <aside className="hidden w-[240px] shrink-0 flex-col border-r border-border bg-surface md:flex"><LayersPanel /></aside>}
        <div className="relative min-w-0 flex-1">{doc ? <EditorCanvas /> : <Skeleton className="m-8 h-[70vh]" />}</div>
        {panels.right && <aside className="scrollbar-thin w-[280px] shrink-0 overflow-y-auto border-l border-border bg-surface max-lg:absolute max-lg:right-0 max-lg:top-0 max-lg:z-20 max-lg:h-full max-lg:shadow-[var(--shadow-pop)]">
          {doc && <PropertiesPanel brandColors={brand?.colors ?? []} />}
        </aside>}
      </div>
      <TemplatesDialog open={templatesOpen} onOpenChange={setTemplatesOpen} />
      <RevisionsDialog open={revisionsOpen} onOpenChange={setRevisionsOpen} docId={id} onRestored={(d, v) => { version.current = v; useEditor.getState().load(d); }} beforeRestore={() => save({ silent: true })} />
      <SaveTemplateDialog open={saveTemplateOpen} onOpenChange={setSaveTemplateOpen} docId={id} defaultName={name} beforeSave={() => save({ silent: true, thumbnail: true })} />
    </div>
  );
}

function TemplatesDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [list, setList] = React.useState<{ id: string; name: string; category: string; width: number; height: number; thumb_url?: string }[]>([]);
  React.useEffect(() => {
    if (!open) return;
    get<typeof list>("/templates").then(async (ts) => {
      setList(ts);
      // Lazily render thumbnails for templates that don't have one yet.
      for (const t of ts.filter((x) => !x.thumb_url)) {
        const r = await post<{ thumb_url: string }>(`/templates/${t.id}/thumbnail`).catch(() => null);
        if (r) setList((p) => p.map((x) => (x.id === t.id ? { ...x, thumb_url: r.thumb_url } : x)));
      }
    });
  }, [open]);
  const apply = async (tid: string, mode: "add" | "replace") => {
    const t = await get<{ document: EditorDoc }>(`/templates/${tid}`);
    const s = useEditor.getState();
    const fresh = t.document.layers.map((l) => ({ ...l, id: crypto.randomUUID().replace(/-/g, "").slice(0, 12), parentId: undefined }));
    if (mode === "replace") s.commit((d) => { d.width = t.document.width; d.height = t.document.height; d.background = t.document.background; d.layers = fresh; });
    else {
      const sx = s.doc!.width / t.document.width, sy = s.doc!.height / t.document.height, k = Math.min(sx, sy);
      s.commit((d) => { d.layers.push(...fresh.map((l) => ({ ...l, x: l.x * k, y: l.y * k, width: l.width * k, height: l.height * k, fontSize: l.fontSize ? l.fontSize * k : l.fontSize, points: l.points?.map((p) => p * k) }))); });
    }
    onOpenChange(false);
    toast.success(mode === "replace" ? "Template applied" : "Template layers added");
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Templates" description="Placeholders like {{headline}} can be replaced with your own text." wide>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {list.map((t) => (
          <div key={t.id} className="overflow-hidden rounded-[12px] border border-border">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {t.thumb_url ? <img src={t.thumb_url} alt={t.name} className="aspect-square w-full bg-sunken object-contain" /> : <Skeleton className="aspect-square rounded-none" />}
            <div className="p-2.5"><div className="truncate text-[13px] font-medium">{t.name}</div><div className="text-[11px] text-muted">{t.category} · {t.width}×{t.height}</div>
              <div className="mt-2 flex gap-1.5"><Button size="sm" variant="outline" onClick={() => apply(t.id, "add")}>Add</Button><Button size="sm" variant="ghost" onClick={() => apply(t.id, "replace")}>Replace all</Button></div></div>
          </div>
        ))}
      </div>
    </Dialog>
  );
}

function RevisionsDialog({ open, onOpenChange, docId, onRestored, beforeRestore }: { open: boolean; onOpenChange: (o: boolean) => void; docId: string; onRestored: (d: EditorDoc, v: number) => void; beforeRestore: () => Promise<void> }) {
  const [list, setList] = React.useState<{ id: string; version: number; created_at: string; layers: number }[]>([]);
  React.useEffect(() => { if (open) get<typeof list>(`/documents/${docId}/revisions`).then(setList); }, [open, docId]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Version history" description="Checkpoints are saved every few minutes and on every manual save.">
      {list.length === 0 ? <div className="py-6 text-center text-[13px] text-muted">No checkpoints yet. Press Save (Ctrl+S) to create one.</div> : (
        <div className="flex flex-col gap-1">
          {list.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-[10px] px-3 py-2 hover:bg-sunken">
              <div className="text-[13px]"><div className="font-medium">Version {r.version}</div><div className="text-xs text-muted">{new Date(r.created_at.endsWith("Z") ? r.created_at : `${r.created_at}Z`).toLocaleString()} · {r.layers} layers</div></div>
              <Button size="sm" variant="outline" onClick={async () => {
                await beforeRestore();
                const res = await post<DocSummary & { document: EditorDoc }>(`/documents/${docId}/revisions/${r.id}/restore`);
                onRestored(res.document, res.version); onOpenChange(false); toast.success(`Restored version ${r.version} (current state saved as a checkpoint)`);
              }}>Restore</Button>
            </div>
          ))}
        </div>
      )}
    </Dialog>
  );
}

function SaveTemplateDialog({ open, onOpenChange, docId, defaultName, beforeSave }: { open: boolean; onOpenChange: (o: boolean) => void; docId: string; defaultName: string; beforeSave: () => Promise<void> }) {
  const [n, setN] = React.useState(defaultName);
  React.useEffect(() => { if (open) setN(defaultName); }, [open, defaultName]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Save as template" description="Reuse this layout for other products — in the editor, Factory or A+ builder."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={async () => { await beforeSave(); await post("/templates", { name: n || "Untitled template", category: "custom", document_id: docId }); toast.success("Template saved"); onOpenChange(false); }}>Save template</Button></>}>
      <Field label="Template name"><Input value={n} onChange={(e) => setN(e.target.value)} /></Field>
    </Dialog>
  );
}
