"use client";
import {
  ArrowRight, CircleCheck, Clapperboard, Cpu, FileText, Images, LayoutTemplate, Package, Palette, PenLine, Sparkles, WandSparkles,
} from "lucide-react";
import Link from "next/link";
import { JobStatusBadge } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardHeader, EmptyState, ErrorState, Notice, Progress, ProviderBadge, Skeleton, Stat } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import type { Asset, Job } from "@/lib/types";
import { cn, providerLabel, timeAgo } from "@/lib/utils";

interface Dashboard {
  counts: Record<string, number>;
  active_brand: { id: string; name: string; colors: string[]; tagline?: string } | null;
  checklist: { key: string; label: string; done: boolean; href: string }[];
  recent_projects: { id: string; name: string; kind: string; updated_at: string; thumb_url?: string | null }[];
  recent_assets: Asset[];
  recent_products: { id: string; name: string; category?: string; thumb_url?: string | null }[];
  jobs: Job[];
  job_counts: Record<string, number>;
  usage: { provider: string; kind: string; calls: number; succeeded: number; failed: number; today: number; avg_latency_ms: number }[];
  ai: { text: boolean; image: boolean };
}

const QUICK = [
  { href: "/listings/new", label: "Listing", desc: "Title, bullets & image set", icon: FileText },
  { href: "/studio", label: "Images", desc: "Main, lifestyle, infographics", icon: Images },
  { href: "/aplus/new", label: "A+ content", desc: "Modules you can edit", icon: LayoutTemplate },
  { href: "/videos/new", label: "Video", desc: "Product slideshow MP4", icon: Clapperboard },
  { href: "/edit", label: "Spot edit", desc: "Remove, replace, extend", icon: WandSparkles },
];

function projectHref(p: { id: string; kind: string }) {
  return { listing: `/listings/${p.id}`, aplus: `/aplus/${p.id}`, video: `/videos/${p.id}` }[p.kind] ?? `/projects/${p.id}`;
}

export default function DashboardPage() {
  const q = useApi<Dashboard>(["dashboard"], "/dashboard", { refetchInterval: 8000 });
  const d = q.data;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const pending = d?.checklist.filter((c) => !c.done) ?? [];
  return (
    <div className="flex flex-col gap-6">
      <section className="relative overflow-hidden rounded-[18px] border border-border bg-surface px-6 py-6 shadow-[var(--shadow-card)] sm:px-8">
        <div className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-[radial-gradient(circle,var(--primary-soft),transparent_70%)]" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="text-xs font-medium uppercase tracking-wider text-muted">{d?.active_brand ? "Working on" : "Welcome"}</div>
            <h1 className="mt-1 text-[28px] font-semibold leading-tight">{d?.active_brand?.name ?? "What should we make today?"}</h1>
            <p className="mt-1 text-[13.5px] text-muted">{d?.active_brand?.tagline ?? "Create listings, images, A+ content and videos — on your machine, with free AI."}</p>
            {d?.active_brand?.colors?.length ? (
              <div className="mt-3 flex gap-1.5">{d.active_brand.colors.map((c) => <span key={c} className="size-5 rounded-full ring-1 ring-border" style={{ background: c }} title={c} />)}</div>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Link href="/create"><Button variant="ai" size="lg"><Sparkles />New creative</Button></Link>
          </div>
        </div>
        <div className="relative mt-6 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
          {QUICK.map((qa) => (
            <Link key={qa.href} href={qa.href} className="group flex items-center gap-3 rounded-[12px] border border-border bg-background px-3 py-2.5 transition hover:border-border-strong hover:bg-surface">
              <span className="flex size-8 items-center justify-center rounded-[9px] bg-primary-soft text-primary"><qa.icon className="size-4" /></span>
              <span className="min-w-0"><span className="block text-[13px] font-semibold">{qa.label}</span><span className="block truncate text-[11.5px] text-muted">{qa.desc}</span></span>
            </Link>
          ))}
        </div>
      </section>

      {d && (!d.ai.text || !d.ai.image) && (
        <Notice tone="warning" icon={<Cpu />}>
          {!d.ai.text && <>No text AI is reachable — start Ollama or add a free key in <Link className="font-medium underline" href="/settings">Settings → AI providers</Link>. </>}
          {!d.ai.image && <>No image AI is enabled — image generation will use plain backdrops until you enable local diffusion or Cloudflare. </>}
          Everything else keeps working.
        </Notice>
      )}

      {pending.length > 0 && (
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold">Get started</h2>
            <span className="text-xs text-muted">{d!.checklist.length - pending.length} of {d!.checklist.length} done</span>
          </div>
          <Progress value={(d!.checklist.length - pending.length) / d!.checklist.length} className="mb-3" />
          <div className="grid gap-2 sm:grid-cols-3">
            {d!.checklist.map((c) => (
              <Link key={c.key} href={c.href} className={cn("flex items-center gap-2.5 rounded-[11px] border border-border px-3 py-2.5 text-[13px] hover:bg-sunken", c.done && "opacity-60")}>
                <CircleCheck className={cn("size-4", c.done ? "text-success" : "text-border-strong")} />
                <span className={cn("flex-1", c.done && "line-through")}>{c.label}</span>
                {!c.done && <ArrowRight className="size-3.5 text-muted" />}
              </Link>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {d ? (<>
          <Stat label="Brands" value={d.counts.brands} icon={<Palette />} />
          <Stat label="Products" value={d.counts.products} icon={<Package />} />
          <Stat label="Projects" value={d.counts.projects} icon={<PenLine />} />
          <Stat label="AI-generated assets" value={d.counts.generated} hint={`${d.counts.assets} assets total`} icon={<Sparkles />} />
        </>) : Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[86px]" />)}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader title="Recent creatives" description="Latest generated and edited images" action={<Link href="/library" className="text-[13px] font-medium text-primary hover:underline">Open library</Link>} />
          <div className="p-5 pt-4">
            {!d ? <div className="grid grid-cols-4 gap-3">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)}</div>
              : d.recent_assets.length === 0 ? <EmptyState icon={<Images />} title="No creatives yet" body="Generated and edited images will appear here." action={<Link href="/studio"><Button size="sm">Open image studio</Button></Link>} />
              : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {d.recent_assets.map((a) => (
                    <Link key={a.id} href={`/library?asset=${a.id}`} className="group overflow-hidden rounded-[12px] border border-border bg-sunken">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={a.thumb_url} alt={a.title} className="aspect-square w-full object-cover transition group-hover:scale-[1.02]" loading="lazy" />
                      <div className="px-2 py-1.5"><div className="truncate text-xs font-medium">{a.title}</div><div className="truncate text-[11px] text-muted">{providerLabel(a.provider)}</div></div>
                    </Link>
                  ))}
                </div>
              )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Generation jobs" description={d ? `${d.job_counts.running ?? 0} running · ${d.job_counts.queued ?? 0} queued · ${d.job_counts.failed ?? 0} failed` : "…"}
            action={<Link href="/jobs" className="text-[13px] font-medium text-primary hover:underline">All jobs</Link>} />
          <div className="flex flex-col gap-1 p-3">
            {!d ? <Skeleton className="h-40" /> : d.jobs.length === 0 ? <div className="px-2 py-8 text-center text-[13px] text-muted">Nothing running. Jobs appear here when you generate.</div>
              : d.jobs.map((j) => (
                <div key={j.id} className="rounded-[10px] px-2 py-2">
                  <div className="flex items-center justify-between gap-2 text-[13px]"><span className="truncate font-medium">{j.label}</span><JobStatusBadge status={j.status} /></div>
                  {j.status === "running" && <Progress value={j.progress} tone="ai" className="mt-1.5" />}
                  <div className="mt-0.5 truncate text-xs text-muted">{j.status === "failed" ? j.error : j.message} · {timeAgo(j.created_at)}</div>
                </div>
              ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader title="Recent projects" action={<Link href="/projects" className="text-[13px] font-medium text-primary hover:underline">All</Link>} />
          <div className="flex flex-col p-3">
            {d?.recent_projects.length === 0 && <div className="px-2 py-6 text-center text-[13px] text-muted">No projects yet.</div>}
            {d?.recent_projects.map((p) => (
              <Link key={p.id} href={projectHref(p)} className="flex items-center gap-3 rounded-[10px] px-2 py-2 hover:bg-sunken">
                <div className="size-9 shrink-0 overflow-hidden rounded-[8px] border border-border bg-sunken">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {p.thumb_url && <img src={p.thumb_url} alt="" className="size-full object-cover" />}
                </div>
                <div className="min-w-0 flex-1"><div className="truncate text-[13px] font-medium">{p.name}</div><div className="text-[11.5px] capitalize text-muted">{p.kind} · {timeAgo(p.updated_at)}</div></div>
              </Link>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Products" action={<Link href="/products" className="text-[13px] font-medium text-primary hover:underline">Catalog</Link>} />
          <div className="flex flex-col p-3">
            {d?.recent_products.length === 0 && <div className="px-2 py-6 text-center text-[13px] text-muted">Add your first product to start generating.</div>}
            {d?.recent_products.map((p) => (
              <Link key={p.id} href={`/products/${p.id}`} className="flex items-center gap-3 rounded-[10px] px-2 py-2 hover:bg-sunken">
                <div className="size-9 shrink-0 overflow-hidden rounded-[8px] border border-border bg-sunken">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {p.thumb_url && <img src={p.thumb_url} alt="" className="size-full object-cover" />}
                </div>
                <div className="min-w-0"><div className="truncate text-[13px] font-medium">{p.name}</div><div className="text-[11.5px] text-muted">{p.category ?? "Uncategorized"}</div></div>
              </Link>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="AI usage" description="Last 30 days, all providers free or local" action={<Link href="/settings?tab=usage" className="text-[13px] font-medium text-primary hover:underline">Details</Link>} />
          <div className="flex flex-col gap-2 p-5 pt-3">
            {d?.usage.length === 0 && <div className="py-6 text-center text-[13px] text-muted">No AI calls yet.</div>}
            {d?.usage.map((u) => (
              <div key={`${u.provider}-${u.kind}`} className="flex items-center justify-between gap-2 text-[13px]">
                <ProviderBadge provider={u.provider} ai />
                <span className="text-muted">{u.kind}</span>
                <span className="tabular-nums">{u.succeeded}<span className="text-muted">/{u.calls}</span></span>
                {u.failed > 0 && <Badge tone="danger">{u.failed} failed</Badge>}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
