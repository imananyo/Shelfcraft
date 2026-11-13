"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Check, PenLine, Play, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { ImageThumb, JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Badge, Card, ErrorState, PageHeader, ProviderBadge, Skeleton } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Job } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Concept { persona: string; angle: string; headline: string; subheadline: string; cta: string; visual: string; hypothesis: string }
interface AdSet {
  id: string; name: string; format: string; goal: string; concepts: Concept[]; personas?: string[]; provenance?: { provider: string; model: string };
  renders: Record<string, { asset_id: string; thumb_url: string; document_id?: string; provider?: string; model?: string }>; jobs: Job[];
}

export default function AdSetPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useApi<AdSet>(["adset", id], `/ads/${id}`, { refetchInterval: 4000 });
  const [sel, setSel] = React.useState<number[]>([]);
  const a = q.data;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!a) return <Skeleton className="h-96" />;
  const active = a.jobs.filter((j) => j.status === "queued" || j.status === "running");
  const isVideo = ["sb_video", "sp_video", "story_ad"].includes(a.format);
  const render = async (indices: number[]) => {
    try { await post(`/ads/${id}/render`, { indices }); toast.success(isVideo ? "Video storyboards created and rendering — see Videos" : "Rendering variants"); qc.invalidateQueries({ queryKey: ["adset", id] }); setSel([]); }
    catch (e) { toast.error((e as Error).message); }
  };
  const byPersona = a.concepts.reduce<Record<string, number[]>>((acc, c, i) => ((acc[c.persona] ??= []).push(i), acc), {});
  return (
    <>
      <PageHeader eyebrow={<Link href="/ads" className="hover:text-foreground">Ads studio</Link>} title={a.name}
        description={<span className="flex flex-wrap items-center gap-2"><Badge>{a.format}</Badge><Badge>goal: {a.goal}</Badge>{a.provenance && <ProviderBadge provider={a.provenance.provider} model={a.provenance.model} ai />}</span>}
        actions={a.concepts.length > 0 && <>
          <Button variant="outline" disabled={!sel.length} onClick={() => render(sel)}><Play />Render selected ({sel.length})</Button>
          <Button variant="ai" onClick={() => render(a.concepts.map((_, i) => i))}><Sparkles />Render all A/B variants</Button>
        </>} />
      {active.map((j) => <div key={j.id} className="mb-3"><JobCard jobId={j.id} compact onDone={() => q.refetch()} /></div>)}
      {a.concepts.length === 0 && !active.length && <Card className="p-6 text-[13px] text-muted">No concepts yet — check the job above or Jobs for errors.</Card>}
      {Object.entries(byPersona).map(([persona, idx]) => (
        <section key={persona} className="mb-6">
          <h2 className="mb-3 text-[15px] font-semibold">{persona}</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {idx.map((i) => {
              const c = a.concepts[i];
              const r = a.renders[String(i)];
              const on = sel.includes(i);
              return (
                <Card key={i} className={cn("flex flex-col overflow-hidden", on && "ring-3 ring-[var(--ring)]")}>
                  {r ? <ImageThumb src={r.thumb_url} alt={c.headline} className="aspect-[1.91] rounded-none border-0 [&_img]:object-contain" /> : null}
                  <div className="flex flex-1 flex-col gap-2 p-4">
                    <div className="flex items-center justify-between"><Badge tone="primary">Variant {String.fromCharCode(65 + i)}</Badge><span className="text-xs text-muted">{c.angle}</span></div>
                    <div className="font-display text-[17px] font-semibold leading-snug">{c.headline}</div>
                    <div className="text-[13px] text-muted">{c.subheadline}</div>
                    <div className="text-xs"><b>CTA:</b> {c.cta} · <b>Visual:</b> {c.visual}</div>
                    <div className="rounded-[8px] bg-sunken px-2.5 py-1.5 text-[11.5px] text-muted"><b>Tests:</b> {c.hypothesis}</div>
                    <div className="mt-auto flex gap-1.5 pt-1">
                      <Button size="sm" variant={on ? "primary" : "outline"} onClick={() => setSel((s) => (on ? s.filter((x) => x !== i) : [...s, i]))}>{on && <Check />}{on ? "Selected" : "Select"}</Button>
                      {r?.document_id && <Link href={`/editor/${r.document_id}`}><Button size="sm" variant="outline"><PenLine />Edit</Button></Link>}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </section>
      ))}
      {isVideo && <p className="text-xs text-muted">Video formats create a storyboard per concept under <Link className="underline" href="/videos">Videos</Link> with the headline, subheadline and CTA as scene captions.</p>}
    </>
  );
}
