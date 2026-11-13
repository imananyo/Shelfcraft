"use client";
import { ArrowDown, ArrowUp, ImagePlus, RotateCw, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { AssetPicker, ImageThumb, JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Card, Notice, PageHeader } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import type { Asset, Job } from "@/lib/types";

export default function SpinPage() {
  const [items, setItems] = React.useState<Asset[]>([]);
  const [picker, setPicker] = React.useState(false);
  const [white, setWhite] = React.useState(true);
  const [fps, setFps] = React.useState(24);
  const [loops, setLoops] = React.useState(3);
  const [title, setTitle] = React.useState("360° spin");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<Asset | null>(null);
  const move = (i: number, d: number) => setItems((s) => { const n = [...s]; const [x] = n.splice(i, 1); n.splice(i + d, 0, x); return n; });
  const start = async () => {
    try { const j = await post<Job>("/videos/spin", { asset_ids: items.map((a) => a.id), white_background: white, fps, loops, title }); setJobId(j.id); setResult(null); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <>
      <PageHeader eyebrow={<Link href="/videos" className="hover:text-foreground">Videos</Link>} title="360° spin"
        description="Build a smooth turntable video from photos taken around your product. Rendered locally with FFmpeg — it uses your real photos, nothing is AI-generated." />
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card className="p-5">
          <Notice className="mb-4 text-[12.5px]">Tip: put the product on a turntable or rotate it by hand, keep the camera still, and take 8–24 photos at even angles. Order them below.</Notice>
          <div className="mb-3 flex items-center justify-between"><span className="text-[13.5px] font-semibold">Angle photos ({items.length})</span>
            <Button size="sm" variant="outline" onClick={() => setPicker(true)}><ImagePlus />Add photo</Button></div>
          {items.length === 0 ? <div className="py-10 text-center text-[13px] text-muted">Add at least 3 photos.</div> : (
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
              {items.map((a, i) => (
                <div key={`${a.id}-${i}`} className="flex flex-col gap-1">
                  <ImageThumb src={a.thumb_url} alt={a.title} className="aspect-square" />
                  <div className="flex items-center justify-between text-[11px] text-muted">
                    <span>#{i + 1}</span>
                    <span className="flex gap-1">
                      <button aria-label="Move earlier" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="size-3.5" /></button>
                      <button aria-label="Move later" disabled={i === items.length - 1} onClick={() => move(i, 1)}><ArrowDown className="size-3.5" /></button>
                      <button aria-label="Remove" onClick={() => setItems((s) => s.filter((_, j) => j !== i))}><X className="size-3.5" /></button>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card className="flex flex-col gap-3 p-5 lg:sticky lg:top-0 lg:self-start">
          <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <label className="flex items-center gap-2 text-[13px]"><Switch checked={white} onChange={setWhite} label="White background" />Remove background (white studio look)</label>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Speed"><Select value={fps} onChange={(e) => setFps(Number(e.target.value))}>{[12, 18, 24, 30].map((n) => <option key={n} value={n}>{n} fps</option>)}</Select></Field>
            <Field label="Loops"><Select value={loops} onChange={(e) => setLoops(Number(e.target.value))}>{[1, 2, 3, 5].map((n) => <option key={n}>{n}</option>)}</Select></Field>
          </div>
          <Button size="lg" onClick={start} disabled={items.length < 3 || !!jobId}><RotateCw />Render 360° video</Button>
          {jobId && <JobCard jobId={jobId} onDone={async (j) => { setJobId(null); setResult(await get<Asset>(`/assets/${j.result?.asset_id}`)); }} />}
          {result && <video src={result.url} controls loop className="w-full rounded-[10px] bg-black" />}
        </Card>
      </div>
      <AssetPicker open={picker} onOpenChange={setPicker} onPick={(a) => setItems((s) => [...s, a])} title="Add an angle photo" />
    </>
  );
}
