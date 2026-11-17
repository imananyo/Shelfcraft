"use client";
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, horizontalListSortingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useQueryClient } from "@tanstack/react-query";
import { Clapperboard, Download, GripVertical, Mic, Music, Pause, Play, Plus, Sparkles, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { ShareButton } from "@/components/share-button";
import { toast } from "sonner";
import { AssetPicker, JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Slider, Textarea } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, Notice, PageHeader, Skeleton } from "@/components/ui/misc";
import { Confirm } from "@/components/ui/overlay";
import { del, download, patch, post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Job } from "@/lib/types";
import { cn, formatBytes, uid } from "@/lib/utils";

interface Scene { id: string; asset_id: string; duration: number; text: string; text_position: "top" | "center" | "bottom"; motion: "zoom_in" | "zoom_out" | "none"; thumb_url?: string | null; missing?: boolean }
interface Video {
  id: string; name: string; aspect: string; transition: string; transition_s: number; text_style: Record<string, unknown>; scenes: Scene[];
  estimated_duration: number; music: { asset_id: string; filename: string; url: string } | null;
  last_render: { asset_id: string; url: string; duration_s: number; size_bytes: number } | null; jobs: Job[]; label: string;
}
const RATIO: Record<string, string> = { "16:9": "aspect-video", "9:16": "aspect-[9/16]", "1:1": "aspect-square", "4:5": "aspect-[4/5]" };

function SceneCard({ s, active, onClick, onRemove }: { s: Scene; active: boolean; onClick: () => void; onRemove: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: s.id });
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className="w-36 shrink-0">
      <div onClick={onClick} className={cn("group relative cursor-pointer overflow-hidden rounded-[10px] border-2", active ? "border-primary" : "border-transparent")}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {s.thumb_url ? <img src={s.thumb_url} alt="" className="aspect-video w-full bg-sunken object-cover" /> : <div className="aspect-video bg-sunken" />}
        <button {...attributes} {...listeners} aria-label="Drag scene" className="absolute left-1 top-1 cursor-grab rounded bg-black/50 p-0.5 text-white"><GripVertical className="size-3.5" /></button>
        <button onClick={(e) => { e.stopPropagation(); onRemove(); }} aria-label="Remove scene" className="absolute right-1 top-1 hidden rounded bg-black/50 p-0.5 text-white group-hover:block"><X className="size-3.5" /></button>
        <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1 text-[10px] text-white">{s.duration}s</span>
      </div>
      <div className="mt-1 truncate text-[11px] text-muted">{s.text || "No text"}</div>
    </div>
  );
}

/** Lightweight in-browser preview (approximation of the FFmpeg render). */
function Preview({ v, scenes }: { v: Video; scenes: Scene[] }) {
  const [i, setI] = React.useState(0);
  const [playing, setPlaying] = React.useState(false);
  React.useEffect(() => {
    if (!playing || !scenes.length) return;
    const t = setTimeout(() => setI((x) => (x + 1) % scenes.length), (scenes[i]?.duration ?? 3) * 1000);
    return () => clearTimeout(t);
  }, [playing, i, scenes]);
  const s = scenes[i];
  return (
    <div className="flex flex-col gap-2">
      <div className={cn("relative mx-auto max-h-[52vh] w-full overflow-hidden rounded-[12px] bg-black", RATIO[v.aspect], v.aspect === "9:16" && "max-w-[300px]", v.aspect === "4:5" && "max-w-[400px]")}>
        {s?.thumb_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={s.id + playing} src={s.thumb_url.replace("/thumb", "/file")} alt="" className="absolute inset-0 size-full object-cover"
            style={{ animation: playing && s.motion !== "none" ? `${s.motion === "zoom_in" ? "kbIn" : "kbOut"} ${s.duration}s linear forwards` : undefined }} />
        )}
        {s?.text && (
          <div className={cn("absolute inset-x-0 bg-black/45 px-4 py-2 text-center text-[15px] font-bold text-white", s.text_position === "top" ? "top-[7%]" : s.text_position === "center" ? "top-1/2 -translate-y-1/2" : "bottom-[8%]")}>{s.text}</div>
        )}
        <style>{`@keyframes kbIn{from{transform:scale(1)}to{transform:scale(1.1)}}@keyframes kbOut{from{transform:scale(1.1)}to{transform:scale(1)}}`}</style>
      </div>
      <div className="flex items-center justify-center gap-2">
        <Button size="sm" variant="outline" onClick={() => setPlaying((p) => !p)} disabled={!scenes.length}>{playing ? <Pause /> : <Play />}{playing ? "Pause" : "Play preview"}</Button>
        <span className="text-xs text-muted">Scene {scenes.length ? i + 1 : 0}/{scenes.length} · preview is approximate</span>
      </div>
    </div>
  );
}

function VoiceoverPanel({ videoId, scenes, open, onJob, existing }: { videoId: string; scenes: number; open: boolean; onJob: (id: string) => void; existing?: string[] }) {
  const voices = useApi<string[]>(["voices"], "/voices");
  const [voice, setVoice] = React.useState("");
  const [rate, setRate] = React.useState(175);
  const [mode, setMode] = React.useState<"ai" | "own">(existing?.length ? "own" : "ai");
  const [script, setScript] = React.useState((existing ?? []).join("\n"));
  const [show, setShow] = React.useState(open);
  const lines = script.split("\n").map((s) => s.trim()).filter(Boolean);
  const start = async () => {
    try {
      const j = await post<Job>(`/videos/${videoId}/voiceover`, { voice, rate, script: mode === "own" ? lines : null });
      onJob(j.id);
      toast.success("Recording voiceover and rendering…");
    } catch (e) { toast.error((e as Error).message); }
  };
  if (!show) return <Button variant="outline" className="mt-6" onClick={() => setShow(true)}><Mic />Add AI voiceover</Button>;
  return (
    <Card className="mt-6 flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <div><h3 className="flex items-center gap-2 text-[15px] font-semibold"><Mic className="size-4 text-ai" />Voiceover video</h3>
          <p className="text-[12.5px] text-muted">Creator-style video: a short script read by an offline Windows voice, with captions. Each scene lasts as long as its line. No on-screen avatar.</p></div>
        <Badge>offline · free</Badge>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Voice"><Select value={voice} onChange={(e) => setVoice(e.target.value)}><option value="">Default</option>{voices.data?.map((v) => <option key={v} value={v.split(" ")[1] ?? v}>{v}</option>)}</Select></Field>
        <Field label={`Speed ${rate} wpm`}><Slider min={130} max={220} step={5} value={rate} onChange={setRate} /></Field>
        <Field label="Script">
          <div className="flex rounded-[10px] border border-border-strong p-0.5 text-[12.5px]">
            <button onClick={() => setMode("ai")} className={cn("flex-1 rounded-[8px] py-1.5", mode === "ai" && "bg-ai-soft text-ai")}>AI writes it</button>
            <button onClick={() => setMode("own")} className={cn("flex-1 rounded-[8px] py-1.5", mode === "own" && "bg-sunken")}>I&apos;ll write it</button>
          </div>
        </Field>
      </div>
      {mode === "own" && (
        <Field label={`One line per scene (${lines.length}/${scenes})`} hint="Short spoken sentences work best (about 8–14 words).">
          <Textarea rows={Math.max(4, scenes)} value={script} onChange={(e) => setScript(e.target.value)} placeholder={"Meet the bottle that keeps up with you.\nCold for 24 hours, hot for 12.\n…"} />
        </Field>
      )}
      {(voices.data?.length ?? 1) === 0 && <Notice tone="warning">No Windows voices were found. Install one in Windows Settings → Time & language → Speech.</Notice>}
      <div className="flex justify-end"><Button variant="ai" onClick={start} disabled={!scenes || (mode === "own" && !lines.length)}><Sparkles />Create voiceover video</Button></div>
    </Card>
  );
}

export default function VideoPage() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useApi<Video>(["video", id], `/videos/${id}`);
  const opts = useApi<{ aspects: string[]; transitions: string[] }>(["video-opts"], "/videos/options");
  const [scenes, setScenes] = React.useState<Scene[]>([]);
  const [sel, setSel] = React.useState<string | null>(null);
  const [picker, setPicker] = React.useState(false);
  const [musicPicker, setMusicPicker] = React.useState(false);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [confirm, setConfirm] = React.useState(false);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));
  const v = q.data;
  React.useEffect(() => {
    if (!v) return;
    setScenes(v.scenes);
    const running = v.jobs.find((j) => j.status === "queued" || j.status === "running");
    if (running) setJobId(running.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v?.id]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["video", id] });

  const saveScenes = async (next: Scene[]) => {
    setScenes(next);
    try { await patch(`/videos/${id}`, { scenes: next.map((s) => ({ id: s.id, asset_id: s.asset_id, duration: s.duration, text: s.text, text_position: s.text_position, motion: s.motion })) }); refresh(); }
    catch (e) { toast.error((e as Error).message); }
  };
  const debounced = React.useRef<ReturnType<typeof setTimeout>>(undefined);
  const updateScene = (sid: string, p: Partial<Scene>) => {
    const next = scenes.map((s) => (s.id === sid ? { ...s, ...p } : s));
    setScenes(next);
    clearTimeout(debounced.current);
    debounced.current = setTimeout(() => saveScenes(next), 600);
  };
  const setting = async (p: Record<string, unknown>) => { try { await patch(`/videos/${id}`, p); refresh(); } catch (e) { toast.error((e as Error).message); } };
  const render = async () => {
    try { const j = await post<Job>(`/videos/${id}/render`); setJobId(j.id); } catch (e) { toast.error((e as Error).message); }
  };
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    saveScenes(arrayMove(scenes, scenes.findIndex((s) => s.id === e.active.id), scenes.findIndex((s) => s.id === e.over!.id)));
  };

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!v) return <Skeleton className="h-96" />;
  const cur = scenes.find((s) => s.id === sel) ?? scenes[0];
  const total = Math.max(0, scenes.reduce((a, s) => a + s.duration, 0) - (scenes.length > 1 && v.transition !== "none" ? v.transition_s * (scenes.length - 1) : 0));

  return (
    <>
      <PageHeader eyebrow={<Link href="/videos" className="hover:text-foreground">Video creator</Link>} title={v.name}
        description={<span className="flex flex-wrap items-center gap-2"><Badge>{v.aspect}</Badge>{scenes.length} scenes · ≈{total.toFixed(1)}s<Badge tone="neutral">{v.label}</Badge></span>}
        actions={<>
          <ShareButton projectId={id} />
          {v.last_render && <Button variant="outline" onClick={() => download(`/assets/${v.last_render!.asset_id}/file?download=true`)}><Download />Download MP4</Button>}
          <Button size="lg" onClick={render} disabled={!scenes.length || !!jobId}><Clapperboard />Render MP4</Button>
          <Button variant="ghost" size="icon" aria-label="Delete video" onClick={() => setConfirm(true)}><Trash2 /></Button>
        </>} />
      {jobId && <div className="mb-4"><JobCard jobId={jobId} title="Rendering video with FFmpeg" onDone={() => { setJobId(null); refresh(); toast.success("Video ready"); }} /></div>}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="flex flex-col gap-5">
          {v.last_render && !jobId ? (
            <Card className="p-4">
              <div className="mb-2 flex items-center justify-between text-[13px]"><span className="font-medium">Latest render</span><span className="text-xs text-muted">{v.last_render.duration_s}s · {formatBytes(v.last_render.size_bytes)}</span></div>
              <video key={v.last_render.asset_id} src={v.last_render.url} controls className={cn("mx-auto max-h-[52vh] rounded-[10px] bg-black", v.aspect === "9:16" ? "max-w-[300px]" : "w-full")} />
            </Card>
          ) : <Card className="p-4"><Preview v={v} scenes={scenes} /></Card>}
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between"><h3 className="text-[14px] font-semibold">Storyboard</h3><Button size="sm" variant="outline" onClick={() => setPicker(true)} disabled={scenes.length >= 30}><Plus />Add scene</Button></div>
            {scenes.length === 0 ? <EmptyState icon={<Clapperboard />} title="No scenes" body="Add product photos or generated creatives as scenes." className="py-8" /> : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
                <SortableContext items={scenes.map((s) => s.id)} strategy={horizontalListSortingStrategy}>
                  <div className="scrollbar-thin flex gap-3 overflow-x-auto pb-2">
                    {scenes.map((s) => <SceneCard key={s.id} s={s} active={cur?.id === s.id} onClick={() => setSel(s.id)} onRemove={() => saveScenes(scenes.filter((x) => x.id !== s.id))} />)}
                  </div>
                </SortableContext>
              </DndContext>
            )}
          </Card>
        </div>
        <div className="flex flex-col gap-4">
          {cur && (
            <Card className="flex flex-col gap-3 p-4">
              <h3 className="text-[13.5px] font-semibold">Scene {scenes.indexOf(cur) + 1}</h3>
              <Field label="Text overlay"><Input value={cur.text} maxLength={200} onChange={(e) => updateScene(cur.id, { text: e.target.value })} placeholder="e.g. Keeps drinks cold 24h" /></Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Position"><Select value={cur.text_position} onChange={(e) => updateScene(cur.id, { text_position: e.target.value as Scene["text_position"] })}><option value="top">Top</option><option value="center">Center</option><option value="bottom">Bottom</option></Select></Field>
                <Field label="Motion"><Select value={cur.motion} onChange={(e) => updateScene(cur.id, { motion: e.target.value as Scene["motion"] })}><option value="zoom_in">Zoom in</option><option value="zoom_out">Zoom out</option><option value="none">Static</option></Select></Field>
              </div>
              <Field label={`Duration ${cur.duration}s`}><Slider min={1} max={10} step={0.5} value={cur.duration} onChange={(d) => updateScene(cur.id, { duration: d })} /></Field>
              {cur.missing && <Notice tone="danger">This scene&apos;s image was deleted. Remove or replace it.</Notice>}
            </Card>
          )}
          <Card className="flex flex-col gap-3 p-4">
            <h3 className="text-[13.5px] font-semibold">Video settings</h3>
            <Field label="Aspect ratio"><Select value={v.aspect} onChange={(e) => setting({ aspect: e.target.value })}>{opts.data?.aspects.map((a) => <option key={a}>{a}</option>)}</Select></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Transition"><Select value={v.transition} onChange={(e) => setting({ transition: e.target.value })}>{opts.data?.transitions.map((t) => <option key={t}>{t}</option>)}</Select></Field>
              <Field label={`Length ${v.transition_s}s`}><Slider min={0.2} max={1.5} step={0.1} value={v.transition_s} onChange={(t) => setting({ transition_s: Math.round(t * 10) / 10 })} /></Field>
            </div>
            <Field label="Text color"><input type="color" value={String(v.text_style.color ?? "#ffffff")} onChange={(e) => setting({ text_style: { ...v.text_style, color: e.target.value } })} className="h-9 w-full rounded-[10px] border border-border-strong" /></Field>
            <Field label="Background music" hint="Use music you own or have a license for. Trimmed and faded to the video length.">
              {v.music ? (
                <div className="flex items-center gap-2 rounded-[10px] border border-border px-2.5 py-2 text-[13px]"><Music className="size-4 text-muted" /><span className="flex-1 truncate">{v.music.filename}</span>
                  <button aria-label="Remove music" onClick={() => setting({ music_asset_id: null })} className="text-muted hover:text-danger"><X className="size-4" /></button></div>
              ) : <Button variant="outline" onClick={() => setMusicPicker(true)}><Music />Add music</Button>}
            </Field>
          </Card>
        </div>
      </div>
      <VoiceoverPanel videoId={id} scenes={scenes.length} open={sp.get("voiceover") === "1"} onJob={setJobId} existing={(v as unknown as { voiceover_script?: string[] }).voiceover_script} />
      <AssetPicker open={picker} onOpenChange={setPicker} title="Add a scene" onPick={(a) => saveScenes([...scenes, { id: uid(10), asset_id: a.id, duration: 3, text: "", text_position: "bottom", motion: scenes.length % 2 ? "zoom_out" : "zoom_in", thumb_url: a.thumb_url }])} />
      <AssetPicker open={musicPicker} onOpenChange={setMusicPicker} kind="audio" title="Choose background music" onPick={(a) => setting({ music_asset_id: a.id })} />
      <Confirm open={confirm} onOpenChange={setConfirm} title="Delete this video project?" body="Rendered MP4s stay in your asset library." onConfirm={async () => { await del(`/videos/${id}`); router.push("/videos"); }} />
    </>
  );
}
