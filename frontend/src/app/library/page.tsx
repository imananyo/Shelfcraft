"use client";
import { useQueryClient } from "@tanstack/react-query";
import {
  Check, Download, FileArchive, Folder, FolderPlus, Heart, Layers, Library, PenLine, Search, Sparkles, Tag, Trash2, Upload, WandSparkles, X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { Field, Input, Select } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, Notice, PageHeader, ProviderBadge, Skeleton } from "@/components/ui/misc";
import { Confirm, Dialog } from "@/components/ui/overlay";
import { del, download, patch, post, upload } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Asset } from "@/lib/types";
import { cn, formatBytes, timeAgo } from "@/lib/utils";

interface FolderRow { id: string; name: string; count: number }
const PRESETS = [["", "Original size"], ["2000x2000", "Listing 2000²"], ["1080x1080", "Square 1080"], ["1080x1350", "Portrait 4:5"], ["1080x1920", "Story 9:16"], ["1200x628", "Sponsored Brand"], ["970x600", "A+ Basic"], ["1464x600", "A+ Premium"]];

function LibraryInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const [q, setQ] = React.useState("");
  const [deb, setDeb] = React.useState("");
  const [kind, setKind] = React.useState("");
  const [source, setSource] = React.useState(sp.get("source") ?? "");
  const [folder, setFolder] = React.useState("");
  const [fav, setFav] = React.useState(false);
  const [ai, setAi] = React.useState("");
  const [sel, setSel] = React.useState<string[]>([]);
  const [open, setOpen] = React.useState<string | null>(sp.get("asset"));
  const [uploading, setUploading] = React.useState(false);
  const [newFolder, setNewFolder] = React.useState(false);
  const [confirmBulk, setConfirmBulk] = React.useState(false);
  React.useEffect(() => { const t = setTimeout(() => setDeb(q), 200); return () => clearTimeout(t); }, [q]);
  const params = new URLSearchParams({ limit: "200" });
  if (deb) params.set("q", deb);
  if (kind) params.set("kind", kind);
  if (source) params.set("source", source);
  if (folder) params.set("folder_id", folder);
  if (fav) params.set("favorite", "true");
  if (ai) params.set("ai", ai);
  const list = useApi<{ items: Asset[]; total: number }>(["assets", params.toString()], `/assets?${params}`);
  const folders = useApi<FolderRow[]>(["folders"], "/assets/folders/all");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["assets"] }); qc.invalidateQueries({ queryKey: ["folders"] }); };
  const onFiles = async (files: File[]) => {
    setUploading(true);
    try { await upload("/assets", files, "files", folder && folder !== "none" ? { folder_id: folder } : undefined); toast.success(`Uploaded ${files.length} file(s)`); refresh(); }
    catch (e) { toast.error((e as Error).message); } finally { setUploading(false); }
  };
  const toggleSel = (id: string) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <>
      <PageHeader title="Asset library" description={list.data ? `${list.data.total} assets · uploads, generated creatives, edits, videos and exports` : "All your files in one place"}
        actions={<><Button onClick={() => document.getElementById("lib-upload")?.click()} loading={uploading}><Upload />Upload</Button>
          <input id="lib-upload" type="file" multiple className="hidden" accept="image/*,video/mp4,audio/*,.pdf,.txt,.md" onChange={(e) => { const f = Array.from(e.target.files ?? []); if (f.length) onFiles(f); e.target.value = ""; }} /></>} />
      {sp.get("decompose") === "1" && <Notice className="mb-4" icon={<Layers />}><b>Image → Layers:</b> click any image, then <b>Split into layers</b>. Shelfcraft reads the text (OCR), cuts out the subject and rebuilds the background — you get an editable design.</Notice>}
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <aside className="flex flex-col gap-1 lg:sticky lg:top-0 lg:self-start">
          {[["", "All assets"], ["none", "Unfiled"]].map(([id, label]) => (
            <button key={id} onClick={() => setFolder(id)} className={cn("flex items-center gap-2 rounded-[9px] px-2.5 py-1.5 text-[13px]", folder === id ? "bg-surface font-medium ring-1 ring-border" : "hover:bg-sunken")}><Library className="size-4 text-muted" />{label}</button>
          ))}
          <div className="mt-3 flex items-center justify-between px-2.5 text-[11px] font-medium uppercase tracking-wider text-muted">Folders<button aria-label="New folder" onClick={() => setNewFolder(true)} className="hover:text-foreground"><FolderPlus className="size-3.5" /></button></div>
          {folders.data?.map((f) => (
            <div key={f.id} className={cn("group flex items-center gap-2 rounded-[9px] px-2.5 py-1.5 text-[13px]", folder === f.id ? "bg-surface font-medium ring-1 ring-border" : "hover:bg-sunken")}>
              <button className="flex flex-1 items-center gap-2 truncate text-left" onClick={() => setFolder(f.id)}
                onDragOver={(e) => e.preventDefault()} onDrop={async (e) => { const id = e.dataTransfer.getData("asset"); if (id) { await patch(`/assets/${id}`, { folder_id: f.id }); refresh(); toast.success(`Moved to ${f.name}`); } }}>
                <Folder className="size-4 text-muted" /><span className="truncate">{f.name}</span><span className="ml-auto text-[11px] text-muted">{f.count}</span>
              </button>
              <button aria-label={`Delete folder ${f.name}`} className="hidden text-muted hover:text-danger group-hover:block" onClick={async () => { await del(`/assets/folders/${f.id}`); if (folder === f.id) setFolder(""); refresh(); }}><X className="size-3.5" /></button>
            </div>
          ))}
          {!folders.data?.length && <p className="px-2.5 text-xs text-muted">Drag assets onto a folder to file them.</p>}
        </aside>
        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="relative min-w-52 flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name…" /></div>
            <Select className="w-32" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Type"><option value="">All types</option><option value="image">Images</option><option value="video">Videos</option><option value="audio">Audio</option><option value="document">Documents</option></Select>
            <Select className="w-36" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source"><option value="">Any source</option><option value="upload">Uploaded</option><option value="generated">Generated</option><option value="edited">Edited</option><option value="export">Exports</option></Select>
            <Select className="w-32" value={ai} onChange={(e) => setAi(e.target.value)} aria-label="AI"><option value="">AI & non-AI</option><option value="true">AI-made</option><option value="false">Non-AI</option></Select>
            <Button variant={fav ? "primary" : "outline"} size="icon" aria-label="Favorites only" onClick={() => setFav((f) => !f)}><Heart /></Button>
          </div>
          {sel.length > 0 && (
            <Card className="mb-4 flex flex-wrap items-center gap-2 px-4 py-2.5">
              <span className="text-[13px] font-medium">{sel.length} selected</span>
              <Button size="sm" variant="outline" onClick={() => download("/assets/zip", { method: "POST", json: { asset_ids: sel, name: "shelfcraft-selection" } }).catch((e) => toast.error(e.message))}><FileArchive />Download ZIP</Button>
              <Select className="h-8 w-44 text-[12.5px]" value="" onChange={async (e) => { if (!e.target.value) return; await Promise.all(sel.map((id) => patch(`/assets/${id}`, { folder_id: e.target.value === "none" ? null : e.target.value }))); refresh(); toast.success("Moved"); }} aria-label="Move to folder">
                <option value="">Move to folder…</option><option value="none">Unfiled</option>{folders.data?.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
              </Select>
              <Button size="sm" variant="ghost" className="text-danger" onClick={() => setConfirmBulk(true)}><Trash2 />Delete</Button>
              <Button size="sm" variant="ghost" onClick={() => setSel([])}>Clear</Button>
            </Card>
          )}
          {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
          {list.isLoading ? <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)}</div>
            : !list.data?.items.length ? (
              <div className="flex flex-col gap-4">
                <EmptyState icon={<Library />} title="Nothing here yet" body="Upload images, music or documents — generated creatives land here automatically." />
                <Dropzone onFiles={onFiles} accept="image/*,video/mp4,audio/*,.pdf,.txt,.md" label="Drop files to upload" />
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
                {list.data.items.map((a) => (
                  <div key={a.id} draggable onDragStart={(e) => e.dataTransfer.setData("asset", a.id)} className={cn("group relative overflow-hidden rounded-[12px] border bg-surface", sel.includes(a.id) ? "border-primary ring-3 ring-[var(--ring)]" : "border-border")}>
                    <button className="block w-full" onClick={() => setOpen(a.id)} aria-label={`Open ${a.title}`}>
                      {a.kind === "image" ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={a.thumb_url} alt={a.title} className="checkerboard aspect-square w-full object-contain" loading="lazy" />
                      ) : <div className="flex aspect-square items-center justify-center bg-sunken text-xs uppercase text-muted">{a.kind}</div>}
                    </button>
                    <button aria-label="Select" onClick={() => toggleSel(a.id)} className={cn("absolute left-2 top-2 flex size-5 items-center justify-center rounded-[6px] border bg-surface/90", sel.includes(a.id) ? "border-primary bg-primary text-white" : "border-border-strong opacity-0 group-hover:opacity-100")}>{sel.includes(a.id) && <Check className="size-3.5" />}</button>
                    {a.favorite && <Heart className="absolute right-2 top-2 size-4 fill-danger text-danger" />}
                    {a.is_ai_generated && <Badge tone="ai" className="absolute bottom-[52px] right-2"><Sparkles />AI</Badge>}
                    <div className="px-2.5 py-2"><div className="truncate text-[12.5px] font-medium">{a.title}</div><div className="text-[11px] text-muted">{a.source} · {timeAgo(a.created_at)}</div></div>
                  </div>
                ))}
              </div>
            )}
        </div>
      </div>
      {open && <AssetDrawer id={open} onClose={() => { setOpen(null); router.replace("/library"); }} onChange={refresh} folders={folders.data ?? []} />}
      <FolderDialog open={newFolder} onOpenChange={setNewFolder} onCreated={refresh} />
      <Confirm open={confirmBulk} onOpenChange={setConfirmBulk} title={`Delete ${sel.length} asset(s)?`} body="They'll be removed from the library and from any product galleries."
        onConfirm={async () => { await Promise.all(sel.map((id) => del(`/assets/${id}`))); setSel([]); setConfirmBulk(false); refresh(); toast.success("Deleted"); }} />
    </>
  );
}

function AssetDrawer({ id, onClose, onChange, folders }: { id: string; onClose: () => void; onChange: () => void; folders: FolderRow[] }) {
  const q = useApi<Asset & { meta_full: Record<string, unknown> }>(["asset", id], `/assets/${id}`);
  const [title, setTitle] = React.useState("");
  const [tags, setTags] = React.useState("");
  const [fmt, setFmt] = React.useState("png");
  const [preset, setPreset] = React.useState("");
  const [maxKb, setMaxKb] = React.useState("");
  const [confirm, setConfirm] = React.useState(false);
  const a = q.data;
  React.useEffect(() => { if (a) { setTitle(a.title); setTags(a.tags.join(", ")); } }, [a]);
  const save = async (p: Partial<Asset>) => { try { await patch(`/assets/${id}`, p); q.refetch(); onChange(); } catch (e) { toast.error((e as Error).message); } };
  const exportAs = async () => {
    const [w, h] = preset ? preset.split("x") : [];
    const p = new URLSearchParams({ format: fmt });
    if (w) { p.set("width", w); p.set("height", h); }
    if (maxKb) p.set("max_kb", maxKb);
    try { const r = await download(`/assets/${id}/convert?${p}`); toast.success(`Exported ${r.width}×${r.height} · ${formatBytes(r.size)}`); } catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <div className="scrollbar-thin flex h-full w-full max-w-xl flex-col overflow-y-auto bg-surface shadow-[var(--shadow-pop)]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-border px-5 py-3"><span className="text-[14px] font-semibold">Asset details</span><Button variant="ghost" size="icon-sm" aria-label="Close" onClick={onClose}><X /></Button></div>
        {!a ? <Skeleton className="m-5 h-96" /> : (
          <div className="flex flex-col gap-4 p-5">
            {a.kind === "image" ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={a.url} alt={a.title} className="checkerboard max-h-[46vh] w-full rounded-[12px] border border-border object-contain" />
            ) : a.kind === "video" ? <video src={a.url} controls className="w-full rounded-[12px] bg-black" /> : a.kind === "audio" ? <audio src={a.url} controls className="w-full" /> : null}
            <div className="flex flex-wrap items-center gap-2">
              <ProviderBadge provider={a.provider} model={a.model} ai={a.is_ai_generated} />
              {a.width && <Badge className="font-mono">{a.width}×{a.height}</Badge>}<Badge>{formatBytes(a.size_bytes)}</Badge><Badge>{a.source}</Badge>
              {a.duration_s ? <Badge>{a.duration_s}s</Badge> : null}
            </div>
            {typeof a.meta_full?.note === "string" && <p className="text-xs text-muted">{a.meta_full.note}</p>}
            {typeof a.meta_full?.prompt === "string" && <div className="rounded-[10px] bg-sunken p-3 font-mono text-[11.5px] text-muted">{a.meta_full.prompt}</div>}
            <div className="flex flex-wrap gap-2">
              <Button variant={a.favorite ? "primary" : "outline"} size="sm" onClick={() => save({ favorite: !a.favorite })}><Heart className={a.favorite ? "fill-current" : ""} />{a.favorite ? "Favorited" : "Favorite"}</Button>
              <Button variant="outline" size="sm" onClick={() => download(`/assets/${a.id}/file?download=true`, {}, a.filename)}><Download />Original</Button>
              {a.kind === "image" && <Link href={`/edit?asset=${a.id}`}><Button variant="outline" size="sm"><WandSparkles />Spot edit</Button></Link>}
              {a.kind === "image" && <SplitLayers assetId={a.id} />}
              {typeof a.meta_full?.document_id === "string" && <Link href={`/editor/${a.meta_full.document_id}`}><Button variant="outline" size="sm"><PenLine />Edit layers</Button></Link>}
              {typeof a.meta_full?.parent_asset_id === "string" && <Link href={`/library?asset=${a.meta_full.parent_asset_id}`}><Button variant="ghost" size="sm">View original</Button></Link>}
            </div>
            <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} onBlur={() => title !== a.title && save({ title })} /></Field>
            <Field label="Tags" hint="Comma separated"><div className="relative"><Tag className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input className="pl-9" value={tags} onChange={(e) => setTags(e.target.value)} onBlur={() => save({ tags: tags.split(",").map((t) => t.trim()).filter(Boolean) })} /></div></Field>
            <Field label="Folder"><Select value={a.folder_id ?? ""} onChange={(e) => save({ folder_id: e.target.value || null })}><option value="">Unfiled</option>{folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</Select></Field>
            {a.kind === "image" && (
              <Card className="flex flex-col gap-3 p-4">
                <div className="text-[13.5px] font-semibold">Export as</div>
                <div className="grid grid-cols-3 gap-2">
                  <Select value={fmt} onChange={(e) => setFmt(e.target.value)} aria-label="Format"><option value="png">PNG</option><option value="jpeg">JPEG</option><option value="webp">WebP</option></Select>
                  <Select value={preset} onChange={(e) => setPreset(e.target.value)} aria-label="Size" className="col-span-2">{PRESETS.map(([v, l]) => <option key={v} value={v}>{l}{v ? ` · ${v}` : ""}</option>)}</Select>
                </div>
                {fmt !== "png" && <Field label="Max file size (KB)" hint="Quality is reduced until it fits"><Input type="number" value={maxKb} onChange={(e) => setMaxKb(e.target.value)} placeholder="Optional, e.g. 1000" /></Field>}
                <p className="text-[11px] text-muted">Size presets resize exactly to the target (aspect may change). Dimensions & file size are reported after export.</p>
                <Button onClick={exportAs}><Download />Export</Button>
              </Card>
            )}
            <div className="text-xs text-muted">Created {new Date(a.created_at.endsWith("Z") ? a.created_at : `${a.created_at}Z`).toLocaleString()} · {a.filename}</div>
            <Button variant="ghost" className="w-fit text-danger" onClick={() => setConfirm(true)}><Trash2 />Delete asset</Button>
          </div>
        )}
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} title="Delete this asset?" onConfirm={async () => { await del(`/assets/${id}`); onChange(); onClose(); }} />
    </div>
  );
}

function SplitLayers({ assetId }: { assetId: string }) {
  const [jobId, setJobId] = React.useState<string | null>(null);
  const router = useRouter();
  if (jobId) return <div className="w-full"><JobCard jobId={jobId} compact title="Splitting into layers (OCR + cut-out)" onDone={(j) => router.push(`/editor/${j.result?.document_id}`)} /></div>;
  return (
    <Button variant="outline" size="sm" onClick={async () => { try { setJobId((await post<{ id: string }>(`/assets/${assetId}/decompose`)).id); } catch (e) { toast.error((e as Error).message); } }}>
      <Layers />Split into layers
    </Button>
  );
}

function FolderDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: () => void }) {
  const [name, setName] = React.useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="New folder" footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
      <Button onClick={async () => { if (!name.trim()) return; await post("/assets/folders", { name }); setName(""); onCreated(); onOpenChange(false); }}>Create</Button></>}>
      <Field label="Folder name"><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Spring campaign" /></Field>
    </Dialog>
  );
}

export default function Page() {
  return <React.Suspense><LibraryInner /></React.Suspense>;
}
