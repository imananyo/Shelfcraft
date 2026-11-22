"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ClipboardList, Copy, Download, Gauge, History, Images, Info, Languages, Layers, LayoutTemplate, RefreshCw, RotateCcw, Save, Sparkles, Trash2, TriangleAlert, Users } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { ShareButton } from "@/components/share-button";
import { toast } from "sonner";
import { AssetResult, JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, ListInput, Select, Textarea } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, Notice, PageHeader, ProviderBadge, Skeleton, TabPanel, Tabs } from "@/components/ui/misc";
import { Confirm, Menu, MenuItem, Popover } from "@/components/ui/overlay";
import { del, download, get, post, put } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Asset, CreativeBrief, ImagePlan, Job, ListingCopy, PlanSlot, SlotStatus, StrategySource } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Listing {
  id: string; name: string; product_id: string; product_name?: string; marketplace: string; options: Record<string, string>;
  copy: ListingCopy | null; warnings: { field: string; message: string }[]; provenance?: { provider?: string; model?: string; edited_by_user?: boolean } | null;
  versions: number; images: { slot: string; asset_id: string; document_id?: string }[]; image_errors: string[];
  limits: Record<string, { max_chars?: number; max_bytes?: number; count?: number; note?: string }>; jobs: Job[];
  image_plan?: ImagePlan | null; image_status?: Record<string, SlotStatus>; brief?: CreativeBrief | null;
}

const SOURCE_LABEL: Record<StrategySource, string> = { hook: "Hook", pain_point: "Pain point", usp: "USP", benefit: "Benefit",
  persona: "Persona", review: "Customer reviews", spec: "Specs" };
const isPending = (st?: SlotStatus) => st?.status === "queued" || st?.status === "running";

const SLOT_LABEL: Record<string, string> = { main_white: "Main image", lifestyle: "Lifestyle", lifestyle_2: "Lifestyle 2", infographic_features: "Feature callouts",
  infographic_benefits: "Benefit headline", comparison: "Comparison", dimensions: "Dimensions", detail: "Detail" };

function Counter({ n, max, unit = "chars" }: { n: number; max?: number; unit?: string }) {
  if (!max) return <span>{n} {unit}</span>;
  return <span className={cn(n > max && "font-medium text-danger")}>{n}/{max} {unit}</span>;
}

/** Guard against AI output in an unexpected shape (e.g. keywords as one string) so the editor never crashes. */
function toList(v: unknown, sep: string): string[] {
  if (Array.isArray(v)) return v.map((x) => (typeof x === "string" ? x : JSON.stringify(x)));
  if (typeof v === "string") return v.split(sep).map((s) => s.trim()).filter(Boolean);
  return [];
}
function toText(v: unknown): string {
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return v.join(" ");
  return v == null ? "" : String(v);
}
function safeCopy(c: ListingCopy): ListingCopy {
  return { ...c, title: toText(c.title), description: toText(c.description), search_terms: toText(c.search_terms),
    bullets: toList(c.bullets, "\n"), keywords: toList(c.keywords, ","), benefits: toList(c.benefits, "\n"),
    listing_structure: toList(c.listing_structure, "\n"), creative_recommendations: toList(c.creative_recommendations, "\n"),
    assumptions: toList(c.assumptions, "\n"),
    feature_explanations: Array.isArray(c.feature_explanations) ? c.feature_explanations.filter((f) => f && typeof f === "object") : [],
    image_strategy: (Array.isArray(c.image_strategy) ? c.image_strategy.filter((s) => s && typeof s === "object") : [])
      .map((s) => ({ ...s, callouts: toList(s.callouts, "\n") })) };
}

function ListingInner() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  // Poll while any image of the set is still queued or rendering (each image is its own job).
  const q = useApi<Listing>(["listing", id], `/listings/${id}`, {
    refetchInterval: (d) => (d && Object.values(d.image_status ?? {}).some(isPending) ? 3000 : false) });
  const [tab, setTab] = React.useState(sp.get("tab") ?? "copy");
  const [copy, setCopy] = React.useState<ListingCopy | null>(null);
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [imgJob, setImgJob] = React.useState<string | null>(null);
  const [planJob, setPlanJob] = React.useState<string | null>(null);
  const [style, setStyle] = React.useState("minimal");
  const [confirmDel, setConfirmDel] = React.useState(false);
  const L = q.data;

  // Jobs this page has already seen finish. The listing data is refetched after a job ends, but until the new data
  // arrives the old copy still lists that job as "running"; without this guard the page re-adopts the finished job,
  // its JobCard fires onDone again at once, and the two loop forever ("Maximum update depth exceeded").
  const finished = React.useRef(new Set<string>());
  const finish = (id: string | null) => { if (id) finished.current.add(id); };

  React.useEffect(() => {
    if (!L) return;
    const active = L.jobs.filter((j) => (j.status === "queued" || j.status === "running") && !finished.current.has(j.id));
    const copyJob = active.find((j) => j.type === "listing_copy");
    const imageJob = active.find((j) => j.type === "listing_images");
    const planningJob = active.find((j) => j.type === "listing_image_plan");
    if (copyJob && !jobId) setJobId(copyJob.id);
    if (imageJob && !imgJob) setImgJob(imageJob.id);
    if (planningJob && !planJob) setPlanJob(planningJob.id);
    if (!dirty) setCopy(L.copy ? safeCopy(L.copy) : { title: "", bullets: ["", "", "", "", ""], description: "", keywords: [], search_terms: "" });
  }, [L, dirty, jobId, imgJob, planJob]);

  const refresh = () => qc.invalidateQueries({ queryKey: ["listing", id] });
  const set = (k: keyof ListingCopy, v: unknown) => { setCopy((c) => ({ ...(c ?? {}), [k]: v })); setDirty(true); };

  const save = async (saveVersion = false) => {
    if (!copy) return;
    setSaving(true);
    try { await put(`/listings/${id}/copy`, { copy, save_version: saveVersion }); setDirty(false); refresh(); toast.success(saveVersion ? "Saved as a new version" : "Saved"); }
    catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };
  const regen = async (field?: string, instruction?: string) => {
    if (dirty) await save();
    try { const j = await post<Job>(`/listings/${id}/generate`, { field: field ?? null, instruction: instruction || null }); setJobId(j.id); }
    catch (e) { toast.error((e as Error).message); }
  };
  const genImages = async (replan = false) => {
    if (dirty) await save();
    try { const j = await post<Job>(`/listings/${id}/images`, { style, replan }); setImgJob(j.id); setTab("images"); }
    catch (e) { toast.error((e as Error).message); }
  };
  const planImages = async (rebuildBrief = false) => {
    if (dirty) await save();
    try { const j = await post<Job>(`/listings/${id}/plan`, { rebuild_brief: rebuildBrief }); setPlanJob(j.id); }
    catch (e) { toast.error((e as Error).message); }
  };
  const copyAll = async () => {
    if (!copy) return;
    const text = [copy.title, "", ...(copy.bullets ?? []).map((b) => `• ${b}`), "", copy.description, "", `Search terms: ${copy.search_terms ?? ""}`].join("\n");
    await navigator.clipboard.writeText(text);
    toast.success("Listing copied to clipboard");
  };

  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!L || !copy) return <Skeleton className="h-[600px]" />;
  const lim = L.limits;
  const searchBytes = new TextEncoder().encode(copy.search_terms ?? "").length;
  const generating = !!jobId;

  return (
    <>
      <PageHeader eyebrow={<Link href="/listings" className="hover:text-foreground">Listing builder</Link>} title={L.name}
        description={<span className="flex flex-wrap items-center gap-2"><Badge className="capitalize">{L.marketplace}</Badge>{L.options.country} · {L.options.language}
          {L.provenance?.provider && <ProviderBadge provider={L.provenance.provider} model={L.provenance.model} ai />}{L.provenance?.edited_by_user && <Badge>Edited by you</Badge>}</span>}
        actions={<>
          <ShareButton projectId={id} />
          <Link href={`/aplus/new?product=${L.product_id ?? ""}`}><Button variant="outline" disabled={!L.product_id}><LayoutTemplate />Add A+ Content</Button></Link>
          <Link href="/scale"><Button variant="outline"><Layers />Scale</Button></Link>
          <Button variant="outline" onClick={copyAll}><Copy />Copy</Button>
          <Menu trigger={<Button variant="outline"><Download />Export</Button>}>
            {(["txt", "csv", "json"] as const).map((f) => <MenuItem key={f} onSelect={() => download(`/listings/${id}/export?format=${f}`)}>{f.toUpperCase()}</MenuItem>)}
          </Menu>
          <Link href={`/grader?listing=${id}`}><Button variant="outline" disabled={!L.copy}><Gauge />Grade</Button></Link>
          <TranslateButton id={id} disabled={!L.copy} />
          <Versions id={id} count={L.versions} onRestore={() => { setDirty(false); refresh(); }} />
          <Button onClick={() => save(false)} loading={saving} disabled={!dirty}><Save />Save</Button>
          <Button variant="ghost" size="icon" aria-label="Delete listing" onClick={() => setConfirmDel(true)}><Trash2 /></Button>
        </>} />
      {jobId && <div className="mb-4"><JobCard jobId={jobId} title="Writing listing copy" onDone={() => { finish(jobId); setJobId(null); setDirty(false); refresh(); }} /></div>}
      <Tabs value={tab} onValueChange={setTab} tabs={[{ value: "copy", label: "Copy" }, { value: "strategy", label: "Strategy & keywords" }, { value: "images", label: "Image set", count: L.images.length }]}>
        <TabPanel value="copy">
          <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
            <div className="flex flex-col gap-5">
              <Card className="p-5">
                <Field label="Title" aside={<Counter n={copy.title?.length ?? 0} max={lim.title?.max_chars} />} hint={lim.title?.note}>
                  <div className="flex gap-2"><Textarea rows={2} value={copy.title ?? ""} onChange={(e) => set("title", e.target.value)} disabled={generating} /><Regen onRegen={(i) => regen("title", i)} disabled={generating} /></div>
                </Field>
              </Card>
              <Card className="p-5">
                <Field label={`Bullet points (${lim.bullets?.count ?? 5})`} aside={<span className="flex items-center gap-2">≤ {lim.bullets?.max_chars} chars each<Regen onRegen={(i) => regen("bullets", i)} disabled={generating} /></span>}>
                  <ListInput multiline value={copy.bullets ?? []} onChange={(v) => set("bullets", v)} max={lim.bullets?.count ?? 5} placeholder="BENEFIT: supporting detail" />
                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-muted">{(copy.bullets ?? []).map((b, i) => <span key={i}>#{i + 1}: <Counter n={b.length} max={lim.bullets?.max_chars} /></span>)}</div>
                </Field>
              </Card>
              <Card className="p-5">
                <Field label="Description" aside={<span className="flex items-center gap-2"><Counter n={copy.description?.length ?? 0} max={lim.description?.max_chars} /><Regen onRegen={(i) => regen("description", i)} disabled={generating} /></span>}>
                  <Textarea rows={8} value={copy.description ?? ""} onChange={(e) => set("description", e.target.value)} disabled={generating} />
                </Field>
              </Card>
              <Card className="grid gap-4 p-5 sm:grid-cols-2">
                <Field label="Search terms" aside={lim.search_terms?.max_bytes ? <Counter n={searchBytes} max={lim.search_terms.max_bytes} unit="bytes" /> : <Counter n={(copy.search_terms ?? "").length} max={lim.search_terms?.max_chars} />} hint={lim.search_terms?.note}>
                  <Textarea rows={3} value={copy.search_terms ?? ""} onChange={(e) => set("search_terms", e.target.value)} />
                </Field>
                <Field label="Keywords" aside={<Regen onRegen={(i) => regen("keywords", i)} disabled={generating} />}>
                  <Textarea rows={3} value={(copy.keywords ?? []).join(", ")} onChange={(e) => set("keywords", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
                </Field>
              </Card>
            </div>
            <div className="flex flex-col gap-4 lg:sticky lg:top-0 lg:self-start">
              <Card className="flex flex-col gap-3 p-4">
                <Button variant="ai" onClick={() => regen()} disabled={generating}><Sparkles />{L.copy ? "Regenerate everything" : "Generate copy"}</Button>
                <Button variant="outline" onClick={() => save(true)} disabled={!dirty}>Save as version</Button>
              </Card>
              {L.warnings.length > 0 && (
                <Notice tone="warning" icon={<TriangleAlert />}><div className="mb-1 font-medium">Length guidance</div>{L.warnings.map((w) => <div key={w.field} className="text-xs">{w.message}</div>)}</Notice>
              )}
              {!!copy.assumptions?.length && <Notice icon={<Info />}><div className="mb-1 font-medium">Assumptions to verify</div><ul className="list-disc pl-4 text-xs">{copy.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></Notice>}
              <Notice icon={<Info />} className="text-xs">Limits shown are guidance, not compliance checks. Verify current marketplace rules before publishing. No SEO ranking is implied.</Notice>
            </div>
          </div>
        </TabPanel>
        <TabPanel value="strategy">
          <div className="grid gap-4 md:grid-cols-2">
            <BriefCard brief={L.brief} busy={!!planJob} onRebuild={() => planImages(true)} />
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Benefits</h3><ul className="list-disc space-y-1 pl-4 text-[13px]">{(copy.benefits ?? []).map((b) => <li key={b}>{b}</li>)}</ul></Card>
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Feature explanations</h3>{(copy.feature_explanations ?? []).map((f) => <div key={f.feature} className="mb-2 text-[13px]"><b>{f.feature}</b> — <span className="text-muted">{f.explanation}</span></div>)}</Card>
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Listing structure</h3><ol className="list-decimal space-y-1 pl-4 text-[13px]">{(copy.listing_structure ?? []).map((b) => <li key={b}>{b}</li>)}</ol></Card>
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Creative recommendations</h3><ul className="list-disc space-y-1 pl-4 text-[13px]">{(copy.creative_recommendations ?? []).map((b) => <li key={b}>{b}</li>)}</ul></Card>
            {L.image_plan?.slots.length ? (
              <Card className="p-5 md:col-span-2">
                <div className="mb-3 flex items-center justify-between"><h3 className="text-[14px] font-semibold">Image plan</h3>
                  <Button size="sm" variant="outline" onClick={() => setTab("images")}>Edit in Image set</Button></div>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {L.image_plan.slots.map((s) => (
                    <div key={s.slot} className="rounded-[12px] border border-border p-3 text-[13px]">
                      <div className="mb-1.5 flex flex-wrap gap-1"><Badge tone="primary">{SLOT_LABEL[s.slot] ?? s.slot}</Badge><Badge tone="ai">{SOURCE_LABEL[s.strategy_source] ?? s.strategy_source}</Badge></div>
                      {s.headline && <div className="font-medium">{s.headline}</div>}
                      <div className="text-muted">{s.strategy_note || s.purpose}</div>
                    </div>
                  ))}
                </div>
              </Card>
            ) : null}
            <Card className="p-5 md:col-span-2">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-[14px] font-semibold">Image ideas from the copy</h3><Regen onRegen={(i) => regen("image_strategy", i)} disabled={generating} /></div>
              <p className="-mt-1 mb-3 text-[12px] text-muted">Written with the listing copy. The image plan uses these only for slots the AI couldn&apos;t plan.</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {(copy.image_strategy ?? []).map((s) => (
                  <div key={s.slot + s.concept} className="rounded-[12px] border border-border p-3 text-[13px]">
                    <Badge tone="primary" className="mb-1.5">{SLOT_LABEL[s.slot] ?? s.slot}</Badge>
                    {s.headline && <div className="font-medium">{s.headline}</div>}<div className="text-muted">{s.concept}</div>
                    {!!s.callouts?.length && <div className="mt-1.5 flex flex-wrap gap-1">{s.callouts.map((c) => <Badge key={c}>{c}</Badge>)}</div>}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </TabPanel>
        <TabPanel value="images"><ImageSet listing={L} style={style} setStyle={setStyle} onGenerate={genImages} jobId={imgJob} onDone={() => { finish(imgJob); setImgJob(null); refresh(); }}
          onPlan={() => planImages(false)} planJob={planJob} onPlanDone={() => { finish(planJob); setPlanJob(null); refresh(); }} onRefresh={refresh} /></TabPanel>
      </Tabs>
      <Confirm open={confirmDel} onOpenChange={setConfirmDel} title="Delete this listing?" body="Generated images stay in your asset library."
        onConfirm={async () => { await del(`/listings/${id}`); qc.invalidateQueries({ queryKey: ["listings"] }); router.push("/listings"); }} />
    </>
  );
}

function TranslateButton({ id, disabled }: { id: string; disabled?: boolean }) {
  const langs = useApi<Record<string, string>>(["languages"], "/languages");
  const [lang, setLang] = React.useState("de");
  const [country, setCountry] = React.useState("DE");
  const [images, setImages] = React.useState(true);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const router = useRouter();
  return (
    <Popover className="w-80 p-3" trigger={<Button variant="outline" disabled={disabled}><Languages />Translate</Button>}>
      <div className="flex flex-col gap-2.5">
        <div className="text-[13px] font-medium">Adapt for a new market</div>
        <div className="grid grid-cols-2 gap-2">
          <Select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">{langs.data && Object.entries(langs.data).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          <Select value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country">{["US", "UK", "DE", "FR", "ES", "IT", "NL", "PL", "SE", "TR", "AE", "IN", "JP", "MX", "CA", "AU"].map((c) => <option key={c}>{c}</option>)}</Select>
        </div>
        <label className="flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={images} onChange={(e) => setImages(e.target.checked)} />Also translate text inside the images</label>
        {jobId ? <JobCard jobId={jobId} compact title="Translating" onDone={(j) => { setJobId(null); router.push(`/listings/${j.result?.project_id}`); }} />
          : <Button size="sm" onClick={async () => { try { const j = await post<Job>(`/listings/${id}/translate`, { language: lang, country, translate_images: images }); setJobId(j.id); } catch (e) { toast.error((e as Error).message); } }}><Languages />Translate listing</Button>}
        <p className="text-[11px] text-muted">Creates a new listing; this one stays unchanged.</p>
      </div>
    </Popover>
  );
}

function Regen({ onRegen, disabled }: { onRegen: (instruction?: string) => void; disabled?: boolean }) {
  const [txt, setTxt] = React.useState("");
  return (
    <Popover trigger={<Button size="icon-sm" variant="ghost" aria-label="Regenerate with AI" disabled={disabled} className="text-ai"><RefreshCw /></Button>} className="w-72 p-3">
      <div className="flex flex-col gap-2">
        <div className="text-[13px] font-medium">Regenerate this field</div>
        <Input value={txt} onChange={(e) => setTxt(e.target.value)} placeholder="Optional: shorter, more playful, mention gift…" />
        <Button variant="ai" size="sm" onClick={() => onRegen(txt)}><Sparkles />Regenerate</Button>
      </div>
    </Popover>
  );
}

function Versions({ id, count, onRestore }: { id: string; count: number; onRestore: () => void }) {
  const [list, setList] = React.useState<{ index: number; title?: string }[]>([]);
  return (
    <Popover className="w-80 p-2" trigger={<Button variant="outline" disabled={!count} onClick={async () => setList(await get(`/listings/${id}/versions`))}><History />Versions{count ? ` (${count})` : ""}</Button>}>
      <div className="max-h-80 overflow-y-auto">
        {list.slice().reverse().map((v) => (
          <button key={v.index} className="w-full rounded-[8px] px-2.5 py-2 text-left text-[13px] hover:bg-sunken"
            onClick={async () => { await post(`/listings/${id}/restore/${v.index}`); toast.success("Version restored (current copy saved as a version)"); onRestore(); }}>
            <div className="text-xs text-muted">Version {v.index + 1}</div><div className="truncate">{v.title || "Untitled"}</div>
          </button>
        ))}
      </div>
    </Popover>
  );
}

function BriefCard({ brief, busy, onRebuild }: { brief?: CreativeBrief | null; busy: boolean; onRebuild: () => void }) {
  return (
    <Card className="p-5 md:col-span-2">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <ClipboardList className="size-4 text-muted" /><h3 className="text-[14px] font-semibold">Creative brief</h3>
        {brief && (brief.ai_pass ? <ProviderBadge provider={brief.provider} model={brief.model} ai /> : <Badge>Assembled from stored analysis (no AI)</Badge>)}
        {brief?.stale && <Badge tone="warning">Out of date — research or product changed</Badge>}
        <Button size="sm" variant="outline" className="ml-auto" onClick={onRebuild} disabled={busy}><RefreshCw />{brief ? "Rebuild brief & plan" : "Build brief & plan"}</Button>
      </div>
      {!brief ? <p className="text-[13px] text-muted">The brief combines product facts, Deep Strategy, review themes and the category benchmark. It&apos;s built the first time you plan or generate images, then reused until one of those changes.</p> : (
        <div className="grid gap-4 text-[13px] md:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            {brief.hook && <div><span className="text-muted">Hook: </span><b>{brief.hook}</b></div>}
            {brief.creative_concept && <div><span className="text-muted">Concept: </span>{brief.creative_concept}</div>}
            {brief.target && <div><span className="text-muted">Speaks to: </span>{brief.target}</div>}
            {!!brief.reviews?.love?.length && <div><span className="text-muted">Customers love: </span>{brief.reviews.love.join(", ")}</div>}
            {!!brief.reviews?.hate?.length && <div><span className="text-muted">Complaints: </span>{brief.reviews.hate.join(", ")}</div>}
            <div className="flex flex-wrap gap-1 pt-1 text-[11px]">
              {[["Deep Strategy", brief.sources?.strategy_id], ["Reviews", brief.sources?.reviews_id], ["Category", brief.sources?.category_id]].map(([l, v]) =>
                <Badge key={l as string} tone={v ? "success" : "neutral"}>{l}: {v ? "used" : "not run"}</Badge>)}
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <div className="text-[12px] font-medium text-muted">Customer needs</div>
            {(brief.customer_needs ?? []).map((n, i) => (
              <div key={i} className="rounded-[10px] border border-border p-2"><b>{n.feature}</b>{n.functional_benefit && <> → {n.functional_benefit}</>}{n.emotional_benefit && <> → <i>{n.emotional_benefit}</i></>}
                {n.problem_solved && <div className="text-[12px] text-muted">Solves: {n.problem_solved}</div>}</div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function ImageSet({ listing, style, setStyle, onGenerate, jobId, onDone, onPlan, planJob, onPlanDone, onRefresh }: {
  listing: Listing; style: string; setStyle: (s: string) => void; onGenerate: (replan?: boolean) => void; jobId: string | null; onDone: () => void;
  onPlan: () => void; planJob: string | null; onPlanDone: () => void; onRefresh: () => void;
}) {
  const [moreJobs, setMoreJobs] = React.useState<string[]>([]);
  const [prompt, setPrompt] = React.useState("");
  const [ctype, setCtype] = React.useState("lifestyle");
  const [busy, setBusy] = React.useState(false);
  const plan = listing.image_plan;
  const pending = Object.values(listing.image_status ?? {}).some(isPending);
  const addMore = async () => {
    setBusy(true);
    try {
      const jobs = await post<Job[]>(`/listings/${listing.id}/images/more`, { prompt, creative_type: ctype, count: 2, style });
      setMoreJobs((j) => [...j, ...jobs.map((x) => x.id)]); setPrompt(""); toast.success("Adding 2 more visuals to this set");
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="flex flex-col gap-5">
      <Card className="flex flex-wrap items-end gap-3 p-4">
        <Field label="Visual style" className="w-48"><Select value={style} onChange={(e) => setStyle(e.target.value)}>{["minimal", "natural", "luxury", "vibrant", "editorial", "tech"].map((s) => <option key={s} className="capitalize">{s}</option>)}</Select></Field>
        <div className="flex-1 text-[12.5px] text-muted">First a plan is written from the creative brief and your brand rules: one image at a time, each tied to a point from the strategy. Review or edit it, then render. Each image renders as its own job and can be retried on its own. With the local AI expect ~1 min per planned image and 30–60 s per AI background.</div>
        <Button variant="outline" onClick={onPlan} disabled={!!planJob || !!jobId || pending}><ClipboardList />{plan ? "Re-plan images" : "Plan images"}</Button>
        <Button variant="ai" onClick={() => onGenerate(false)} disabled={!!jobId || !!planJob || pending}><Images />{listing.images.length ? "Regenerate image set" : plan ? "Render image set" : "Plan & generate image set"}</Button>
      </Card>
      {planJob && <JobCard jobId={planJob} title="Writing the creative brief and image plan" onDone={onPlanDone} />}
      {jobId && <JobCard jobId={jobId} title="Preparing the image set" onDone={onDone} />}
      {moreJobs.map((j) => <JobCard key={j} jobId={j} compact title="Adding a visual" onDone={() => { setMoreJobs((x) => x.filter((y) => y !== j)); onDone(); }} />)}
      {plan?.slots.length ? <PlanEditor listing={listing} style={style} onChange={onRefresh} locked={!!planJob || !!jobId} />
        : !planJob && <EmptyState icon={<ClipboardList />} title="No image plan yet" body="Plan images to see what each image will show and why, before anything is rendered. Generating the set plans first automatically." />}
      {listing.image_errors.length > 0 && <Notice tone="warning">Some images couldn&apos;t be created: {listing.image_errors.join("; ")}. Use Retry on that image in the plan above.</Notice>}
      {listing.images.length > 0 && <ListingImages listingId={listing.id} name={listing.name} ids={listing.images} onChange={onDone} />}
      {listing.images.length > 0 && (
        <Card className="flex flex-col gap-3 p-4">
          <div className="text-[14px] font-semibold">Add more visuals</div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Select value={ctype} onChange={(e) => setCtype(e.target.value)} className="sm:w-48" aria-label="Visual type">
              {[["lifestyle", "Lifestyle"], ["hero", "Premium hero"], ["studio", "Studio photo"], ["detail", "Detail close-up"], ["feature", "Feature callouts"], ["infographic", "Benefit infographic"], ["comparison", "Comparison chart"], ["dimensions", "Dimensions"], ["steps", "How-to steps"], ["lifestyle_headline", "Lifestyle + headline"], ["white_bg_main", "White-background main"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Input value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe what you want — e.g. in a gym bag next to a towel" className="flex-1" />
            <Button variant="ai" loading={busy} onClick={addMore}><Sparkles />Add 2 visuals</Button>
          </div>
        </Card>
      )}
    </div>
  );
}

function PlanEditor({ listing, style, onChange, locked }: { listing: Listing; style: string; onChange: () => void; locked: boolean }) {
  // Unsaved edits; null = show the saved plan (so a re-plan or refetch shows up without syncing state in an effect).
  const [edits, setEdits] = React.useState<PlanSlot[] | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [queued, setQueued] = React.useState<Record<string, string>>({});
  const slots = edits ?? listing.image_plan?.slots ?? [];
  const dirty = edits !== null;
  // A retry counts as in flight until the slot's recorded job is that retry and has finished.
  const retrying = Object.fromEntries(Object.entries(queued).filter(([slot, jid]) => {
    const st = listing.image_status?.[slot];
    return !(st?.job_id === jid && !isPending(st));
  }));
  const upd = (i: number, patch: Partial<PlanSlot>) => setEdits(slots.map((s, n) => (n === i ? { ...s, ...patch } : s)));
  const save = async () => {
    setSaving(true);
    try { await put(`/listings/${listing.id}/plan`, { slots }); setEdits(null); onChange(); toast.success("Image plan saved"); }
    catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };
  const retry = async (slot: string) => {
    if (dirty) await save();
    try { const j = await post<Job>(`/listings/${listing.id}/images/${slot}/retry`, { style }); setQueued((r) => ({ ...r, [slot]: j.id })); }
    catch (e) { toast.error((e as Error).message); }
  };
  const plan = listing.image_plan!;
  return (
    <Card className="flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[14px] font-semibold">Image plan</h3>
        {plan.edited_by_user && <Badge>Edited by you</Badge>}
        {plan.brand_rules ? <Badge tone="success">Brand rules applied</Badge> : <Badge>No brand rules yet — add them on the brand page</Badge>}
        <Button size="sm" className="ml-auto" onClick={save} loading={saving} disabled={!dirty || locked}><Save />Save plan</Button>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {slots.map((s, i) => {
          const live = listing.image_status?.[s.slot];
          // A just-queued retry shows "Queued" until the job itself records the slot's status.
          const st: SlotStatus | undefined = retrying[s.slot] && live?.job_id !== retrying[s.slot] ? { status: "queued" } : live;
          const hasText = s.slot !== "main_white";
          return (
            <div key={s.slot} className="flex flex-col gap-2 rounded-[12px] border border-border p-3 text-[13px]">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="primary">{SLOT_LABEL[s.slot] ?? s.slot}</Badge>
                <Badge tone={s.source === "ai" ? "ai" : "neutral"}>{s.source === "ai" ? "AI plan" : s.source === "user" ? "Your edit" : s.source === "auto" ? "Automatic" : "Fallback (no AI)"}</Badge>
                {s.people && <Badge><Users />People</Badge>}
                <span className="ml-auto">
                  {st?.status === "done" && <Badge tone="success">Rendered</Badge>}
                  {st?.status === "queued" && <Badge>Queued</Badge>}
                  {st?.status === "running" && <Badge tone="ai">Rendering {Math.round((st.progress ?? 0) * 100)}%</Badge>}
                  {st?.status === "failed" && <Badge tone="danger">Failed</Badge>}
                </span>
              </div>
              <div className="text-[12px] text-muted">{s.purpose}</div>
              {hasText && <Input value={s.headline} onChange={(e) => upd(i, { headline: e.target.value })} placeholder="Headline on the image" aria-label={`${s.slot} headline`} disabled={locked} />}
              {hasText && <Input value={s.callouts.join(", ")} onChange={(e) => upd(i, { callouts: e.target.value.split(",").map((c) => c.trimStart()) })}
                onBlur={() => upd(i, { callouts: s.callouts.map((c) => c.trim()).filter(Boolean) })} placeholder="Callouts, comma-separated" aria-label={`${s.slot} callouts`} disabled={locked} />}
              <Textarea rows={2} value={s.concept} onChange={(e) => upd(i, { concept: e.target.value })} placeholder="Scene / background for the image model" aria-label={`${s.slot} scene`} disabled={locked} />
              <div className="flex flex-wrap items-center gap-2">
                <Select value={s.strategy_source} onChange={(e) => upd(i, { strategy_source: e.target.value as StrategySource })} className="w-36" aria-label="Strategy point" disabled={locked}>
                  {Object.entries(SOURCE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
                {hasText && s.slot !== "dimensions" && s.slot !== "detail" && <label className="flex items-center gap-1.5 text-[12px]"><input type="checkbox" checked={s.people} onChange={(e) => upd(i, { people: e.target.checked })} disabled={locked} />Person in scene</label>}
              </div>
              <Input value={s.strategy_note} onChange={(e) => upd(i, { strategy_note: e.target.value })} placeholder="Which point of the brief this image proves" aria-label={`${s.slot} strategy note`} disabled={locked} />
              {s.flags.map((f) => <Notice key={f} tone="warning" icon={<TriangleAlert />} className="text-xs">{f}</Notice>)}
              {st?.status === "failed" && st.error && <div className="text-[12px] text-danger">{st.error}</div>}
              {retrying[s.slot] && <JobCard jobId={retrying[s.slot]} compact title={`Rendering ${SLOT_LABEL[s.slot] ?? s.slot}`} onDone={onChange} />}
              {!retrying[s.slot] && !isPending(st) && (
                <Button size="sm" variant="ghost" className="self-start" onClick={() => retry(s.slot)} disabled={locked}><RotateCcw />{st?.status === "failed" ? "Retry this image" : st?.status === "done" ? "Re-render this image" : "Render this image"}</Button>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function ListingImages({ listingId, name, ids, onChange }: { listingId: string; name: string; ids: { slot: string; asset_id: string }[]; onChange: () => void }) {
  const [assets, setAssets] = React.useState<Record<string, Asset>>({});
  const [layout, setLayout] = React.useState<"grid" | "list">("grid");
  const [selecting, setSelecting] = React.useState(false);
  const [sel, setSel] = React.useState<Set<string>>(new Set());
  const [confirm, setConfirm] = React.useState(false);
  React.useEffect(() => {
    let alive = true;
    Promise.all(ids.map((i) => get<Asset>(`/assets/${i.asset_id}`).catch(() => null))).then((list) => {
      if (alive) setAssets(Object.fromEntries(list.filter(Boolean).map((a) => [a!.id, a!])));
    });
    return () => { alive = false; };
  }, [ids]);
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const chosen = [...sel];
  const zip = async (list: string[]) => { try { await download("/assets/zip", { method: "POST", json: { asset_ids: list, name } }, `${name}.zip`); } catch (e) { toast.error((e as Error).message); } };
  const remove = async () => {
    try { await post(`/listings/${listingId}/images/remove`, { asset_ids: chosen }); setSel(new Set()); setSelecting(false); toast.success(`Removed ${chosen.length} visual(s)`); onChange(); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-[10px] border border-border p-0.5" role="group" aria-label="Layout">
          {(["grid", "list"] as const).map((l) => <button key={l} type="button" onClick={() => setLayout(l)} className={cn("rounded-[8px] px-2.5 py-1 text-[12.5px] capitalize", layout === l ? "bg-sunken font-medium text-foreground" : "text-muted")}>{l}</button>)}
        </div>
        <Button size="sm" variant={selecting ? "primary" : "outline"} onClick={() => { setSelecting(!selecting); setSel(new Set()); }}>{selecting ? "Done" : "Select"}</Button>
        {selecting && <>
          <Button size="sm" variant="ghost" onClick={() => setSel(new Set(ids.map((i) => i.asset_id)))}>Select all</Button>
          <Button size="sm" variant="outline" disabled={!chosen.length} onClick={() => zip(chosen)}><Download />Download {chosen.length || ""}</Button>
          <Button size="sm" variant="outline" disabled={!chosen.length} onClick={() => setConfirm(true)}><Trash2 />Remove {chosen.length || ""}</Button>
        </>}
        {!selecting && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => zip(ids.map((i) => i.asset_id))}><Download />Download all</Button>}
      </div>
      <div className={layout === "grid" ? "grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4" : "flex flex-col gap-3"}>
        {ids.map((i) => assets[i.asset_id] ? (
          <div key={i.asset_id} className={cn("relative flex gap-1.5", layout === "grid" ? "flex-col" : "flex-row items-start [&>div:last-child]:max-w-xs")}>
            <div className="flex items-center gap-2">
              {selecting && <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={sel.has(i.asset_id)} onChange={() => toggle(i.asset_id)} aria-label={`Select ${assets[i.asset_id].title}`} />}
              <Badge tone="primary" className="w-fit">{SLOT_LABEL[i.slot] ?? (i.slot === "extra" ? "Added" : i.slot)}</Badge>
            </div>
            <AssetResult asset={assets[i.asset_id]} selected={sel.has(i.asset_id)} onSelect={selecting ? () => toggle(i.asset_id) : undefined} />
          </div>
        ) : <Skeleton key={i.asset_id} className="aspect-[3/4]" />)}
      </div>
      <Confirm open={confirm} onOpenChange={setConfirm} title={`Remove ${chosen.length} visual(s)?`} body="They're removed from this set and moved to the library's trash." confirmLabel="Remove" destructive onConfirm={remove} />
    </div>
  );
}

export default function Page() {
  return <React.Suspense><ListingInner /></React.Suspense>;
}
