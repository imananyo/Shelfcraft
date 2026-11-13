"use client";
import { Boxes, ImageIcon, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { QuickAddProduct } from "@/components/quick-add-product";
import { ImageThumb, JobCard, ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Badge, Card, EmptyState, Notice, PageHeader, ProviderBadge } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Job } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

interface Concept { name: string; big_idea: string; structure: string; materials: string; palette: string[]; typography?: string; front_panel_copy?: string; unboxing?: string; sustainability?: string; best_for?: string; cost_level?: string }
interface Pack { id: string; name: string; concepts: Concept[]; assumptions?: string[]; provider?: string; model?: string; render_urls: Record<string, string> }

function PackagingInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const [productId, setProductId] = React.useState("");
  const [count, setCount] = React.useState(15);
  const [notes, setNotes] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [renders, setRenders] = React.useState<Record<number, string>>({});
  const pid = sp.get("project");
  const list = useApi<{ id: string; name: string; count: number; created_at: string }[]>(["packaging"], "/labs/packaging");
  const pack = useApi<Pack>(["packaging", pid], pid ? `/labs/packaging/${pid}` : null, { refetchInterval: 5000 });
  const start = async () => {
    try { const j = await post<Job>("/labs/packaging", { product_id: productId, count, notes }); setJobId(j.id); }
    catch (e) { toast.error((e as Error).message); }
  };
  const render = async (i: number) => {
    try { const j = await post<Job>(`/labs/packaging/${pid}/render/${i}`); setRenders((r) => ({ ...r, [i]: j.id })); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <>
      <PageHeader eyebrow={<Link href="/labs" className="hover:text-foreground">Labs</Link>} title="Packaging Idea Generator" description="Packaging concepts — structure, materials, palette, front-panel copy and unboxing — grounded in your product." />
      {!pid ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <Card className="flex flex-col gap-3 p-5">
            <Field label="Which product should we work on?" aside={<QuickAddProduct onCreated={setProductId} />}><ProductSelect value={productId} onChange={setProductId} /></Field>
            <div className="grid grid-cols-[120px_1fr] gap-3">
              <Field label="Concepts"><Select value={count} onChange={(e) => setCount(Number(e.target.value))}>{[5, 8, 10, 15].map((n) => <option key={n}>{n}</option>)}</Select></Field>
              <Field label="Notes"><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. plastic-free, giftable, retail shelf" /></Field>
            </div>
            <Button variant="ai" size="lg" disabled={!productId || !!jobId} onClick={start}><Sparkles />Generate packaging ideas</Button>
            {jobId && <JobCard jobId={jobId} onDone={(j) => { setJobId(null); router.push(`/labs/packaging?project=${j.result?.project_id}`); }} />}
          </Card>
          <Card className="p-4">
            <h3 className="mb-2 text-[13.5px] font-semibold">Previous runs</h3>
            {!list.data?.length ? <p className="text-[13px] text-muted">None yet.</p> : list.data.map((r) => (
              <Link key={r.id} href={`/labs/packaging?project=${r.id}`} className="block rounded-[9px] px-2 py-1.5 text-[13px] hover:bg-sunken">{r.name}<span className="block text-[11px] text-muted">{r.count} concepts · {timeAgo(r.created_at)}</span></Link>
            ))}
          </Card>
        </div>
      ) : !pack.data ? <EmptyState icon={<Boxes />} title="Loading…" body="" /> : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2"><h2 className="text-[16px] font-semibold">{pack.data.name}</h2>{pack.data.provider && <ProviderBadge provider={pack.data.provider} model={pack.data.model} ai />}
            <Link href="/labs/packaging" className="ml-auto text-[13px] text-primary hover:underline">New run</Link></div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {pack.data.concepts.map((c, i) => (
              <Card key={i} className="flex flex-col overflow-hidden">
                {pack.data!.render_urls[String(i)] ? <ImageThumb src={pack.data!.render_urls[String(i)]} alt={c.name} className="aspect-square rounded-none border-0" />
                  : <div className="flex h-16">{(c.palette ?? []).slice(0, 4).map((h) => <div key={h} className="flex-1" style={{ background: h }} />)}</div>}
                <div className="flex flex-1 flex-col gap-1.5 p-4 text-[13px]">
                  <div className="flex items-center justify-between"><h3 className="text-[14.5px] font-semibold">{c.name}</h3>{c.cost_level && <Badge>{c.cost_level} cost</Badge>}</div>
                  <p>{c.big_idea}</p>
                  <div className="text-muted"><b className="text-foreground">Structure:</b> {c.structure} · <b className="text-foreground">Materials:</b> {c.materials}</div>
                  {c.front_panel_copy && <div className="rounded-[8px] bg-sunken px-2.5 py-1.5 italic">“{c.front_panel_copy}”</div>}
                  {c.sustainability && <div className="text-xs text-muted">♻ {c.sustainability}</div>}
                  <div className="mt-auto pt-2">
                    {renders[i] ? <JobCard jobId={renders[i]} compact onDone={() => pack.refetch()} />
                      : <Button size="sm" variant="outline" onClick={() => render(i)}><ImageIcon />{pack.data!.render_urls[String(i)] ? "Re-render mock-up" : "Render AI mock-up"}</Button>}
                  </div>
                </div>
              </Card>
            ))}
          </div>
          {!!pack.data.assumptions?.length && <Notice tone="warning" className="mt-4">Assumptions: {pack.data.assumptions.join(" · ")}</Notice>}
          <Notice className="mt-3 text-xs">Mock-ups are AI concept renders — text on them is illustrative. Use the editor for real packaging artwork.</Notice>
        </>
      )}
    </>
  );
}

export default function Page() {
  return <React.Suspense><PackagingInner /></React.Suspense>;
}
