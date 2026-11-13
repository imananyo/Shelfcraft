"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Copy, Download, Gauge, History, Images, Info, Languages, RefreshCw, Save, Sparkles, Trash2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { AssetResult, JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, ListInput, Select, Textarea } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, Notice, PageHeader, ProviderBadge, Skeleton, TabPanel, Tabs } from "@/components/ui/misc";
import { Confirm, Menu, MenuItem, Popover } from "@/components/ui/overlay";
import { del, download, get, post, put } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Asset, Job, ListingCopy } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Listing {
  id: string; name: string; product_id: string; product_name?: string; marketplace: string; options: Record<string, string>;
  copy: ListingCopy | null; warnings: { field: string; message: string }[]; provenance?: { provider?: string; model?: string; edited_by_user?: boolean } | null;
  versions: number; images: { slot: string; asset_id: string; document_id?: string }[]; image_errors: string[];
  limits: Record<string, { max_chars?: number; max_bytes?: number; count?: number; note?: string }>; jobs: Job[];
}

const SLOT_LABEL: Record<string, string> = { main_white: "Main image", lifestyle: "Lifestyle", lifestyle_2: "Lifestyle 2", infographic_features: "Feature callouts",
  infographic_benefits: "Benefit headline", comparison: "Comparison", dimensions: "Dimensions", detail: "Detail" };

function Counter({ n, max, unit = "chars" }: { n: number; max?: number; unit?: string }) {
  if (!max) return <span>{n} {unit}</span>;
  return <span className={cn(n > max && "font-medium text-danger")}>{n}/{max} {unit}</span>;
}

function ListingInner() {
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useApi<Listing>(["listing", id], `/listings/${id}`);
  const [tab, setTab] = React.useState(sp.get("tab") ?? "copy");
  const [copy, setCopy] = React.useState<ListingCopy | null>(null);
  const [dirty, setDirty] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [imgJob, setImgJob] = React.useState<string | null>(null);
  const [style, setStyle] = React.useState("minimal");
  const [confirmDel, setConfirmDel] = React.useState(false);
  const L = q.data;

  React.useEffect(() => {
    if (!L) return;
    const running = L.jobs.find((j) => (j.status === "queued" || j.status === "running"));
    if (running && !jobId && running.type === "listing_copy") setJobId(running.id);
    if (running && !imgJob && running.type === "listing_images") setImgJob(running.id);
    if (!dirty) setCopy(L.copy ?? { title: "", bullets: ["", "", "", "", ""], description: "", keywords: [], search_terms: "" });
  }, [L, dirty, jobId, imgJob]);

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
  const genImages = async () => {
    if (dirty) await save();
    try { const j = await post<Job>(`/listings/${id}/images`, { style }); setImgJob(j.id); setTab("images"); }
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
      {jobId && <div className="mb-4"><JobCard jobId={jobId} title="Writing listing copy" onDone={() => { setJobId(null); setDirty(false); refresh(); }} /></div>}
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
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Benefits</h3><ul className="list-disc space-y-1 pl-4 text-[13px]">{(copy.benefits ?? []).map((b) => <li key={b}>{b}</li>)}</ul></Card>
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Feature explanations</h3>{(copy.feature_explanations ?? []).map((f) => <div key={f.feature} className="mb-2 text-[13px]"><b>{f.feature}</b> — <span className="text-muted">{f.explanation}</span></div>)}</Card>
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Listing structure</h3><ol className="list-decimal space-y-1 pl-4 text-[13px]">{(copy.listing_structure ?? []).map((b) => <li key={b}>{b}</li>)}</ol></Card>
            <Card className="p-5"><h3 className="mb-2 text-[14px] font-semibold">Creative recommendations</h3><ul className="list-disc space-y-1 pl-4 text-[13px]">{(copy.creative_recommendations ?? []).map((b) => <li key={b}>{b}</li>)}</ul></Card>
            <Card className="p-5 md:col-span-2">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-[14px] font-semibold">Image strategy</h3><Regen onRegen={(i) => regen("image_strategy", i)} disabled={generating} /></div>
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
        <TabPanel value="images"><ImageSet listing={L} style={style} setStyle={setStyle} onGenerate={genImages} jobId={imgJob} onDone={() => { setImgJob(null); refresh(); }} /></TabPanel>
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

function ImageSet({ listing, style, setStyle, onGenerate, jobId, onDone }: { listing: Listing; style: string; setStyle: (s: string) => void; onGenerate: () => void; jobId: string | null; onDone: () => void }) {
  return (
    <div className="flex flex-col gap-5">
      <Card className="flex flex-wrap items-end gap-3 p-4">
        <Field label="Visual style" className="w-48"><Select value={style} onChange={(e) => setStyle(e.target.value)}>{["minimal", "natural", "luxury", "vibrant", "editorial", "tech"].map((s) => <option key={s} className="capitalize">{s}</option>)}</Select></Field>
        <div className="flex-1 text-[12.5px] text-muted">Creates the full marketplace set: main image on white, lifestyle, feature & benefit infographics, comparison, dimensions and detail. Every image is saved as an editable layered design. On this CPU expect roughly 30–60 s per AI background.</div>
        <Button variant="ai" onClick={onGenerate} disabled={!!jobId}><Images />{listing.images.length ? "Regenerate image set" : "Generate image set"}</Button>
      </Card>
      {jobId && <JobCard jobId={jobId} title="Building image set" onDone={onDone} />}
      {listing.image_errors.length > 0 && <Notice tone="warning">Some images couldn&apos;t be created: {listing.image_errors.join("; ")}</Notice>}
      {listing.images.length === 0 && !jobId ? <EmptyState icon={<Images />} title="No images yet" body="Generate the set above. The copy's image strategy is used for headlines and callouts." />
        : <ListingImages ids={listing.images} />}
    </div>
  );
}

function ListingImages({ ids }: { ids: { slot: string; asset_id: string }[] }) {
  const [assets, setAssets] = React.useState<Record<string, Asset>>({});
  React.useEffect(() => {
    let alive = true;
    Promise.all(ids.map((i) => get<Asset>(`/assets/${i.asset_id}`).catch(() => null))).then((list) => {
      if (alive) setAssets(Object.fromEntries(list.filter(Boolean).map((a) => [a!.id, a!])));
    });
    return () => { alive = false; };
  }, [ids]);
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
      {ids.map((i) => assets[i.asset_id] ? (
        <div key={i.asset_id} className="flex flex-col gap-1.5"><Badge tone="primary" className="w-fit">{SLOT_LABEL[i.slot] ?? i.slot}</Badge><AssetResult asset={assets[i.asset_id]} /></div>
      ) : <Skeleton key={i.asset_id} className="aspect-[3/4]" />)}
    </div>
  );
}

export default function Page() {
  return <React.Suspense><ListingInner /></React.Suspense>;
}
