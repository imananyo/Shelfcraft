"use client";
import { useQueryClient } from "@tanstack/react-query";
import {
  Copy, Crown, FileText, Lightbulb, MessageSquareQuote, MoreHorizontal, Plus, ShieldQuestion, Sparkles, Target, Trash2, TrendingUp, Users, X,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { BrowserPageImport } from "@/components/browser-page-import";
import { ProductCompetitors } from "@/components/product-competitors";
import { ProductReviews } from "@/components/product-reviews";
import { AssetResult, BrandSelect, ImageThumb, JobCard } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { Field, Input, ListInput, Textarea } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, Notice, PageHeader, ProviderBadge, Skeleton, TabPanel, Tabs } from "@/components/ui/misc";
import { Confirm, Menu, MenuItem, MenuSeparator } from "@/components/ui/overlay";
import { del, patch, post, put, upload } from "@/lib/api";
import { useApi, useCapabilities } from "@/lib/hooks";
import type { Asset, Job, Product, Variant } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useApi<Product>(["product", id], `/products/${id}`);
  const [tab, setTab] = React.useState(search.get("tab") ?? "details");
  const [confirm, setConfirm] = React.useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["product", id] }); qc.invalidateQueries({ queryKey: ["products"] }); };
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const p = q.data;
  return (
    <>
      <PageHeader eyebrow={<Link href="/products" className="hover:text-foreground">Products</Link>} title={p?.name ?? <Skeleton className="h-8 w-64" />}
        description={p ? `${p.category ?? "Uncategorized"}${p.sku ? ` · SKU ${p.sku}` : ""} · updated ${timeAgo(p.updated_at)}` : undefined}
        actions={p && <>
          <Link href={`/listings/new?product=${p.id}`}><Button variant="ai"><Sparkles />Create listing</Button></Link>
          <Link href={`/studio?product=${p.id}`}><Button variant="outline">Generate images</Button></Link>
          <Menu trigger={<Button variant="ghost" size="icon" aria-label="More"><MoreHorizontal /></Button>}>
            <MenuItem icon={<Copy />} onSelect={async () => { const n = await post<Product>(`/products/${p.id}/duplicate`); toast.success("Duplicated"); router.push(`/products/${n.id}`); }}>Duplicate</MenuItem>
            <MenuItem icon={<FileText />} onSelect={() => router.push(`/videos/new?product=${p.id}`)}>Make a video</MenuItem>
            <MenuSeparator />
            <MenuItem icon={<Trash2 />} destructive onSelect={() => setConfirm(true)}>Delete product</MenuItem>
          </Menu>
        </>} />
      {p && (p.tags ?? []).some((t) => t === "amazon" || t === "walmart") && !p.description && !p.features?.length && (
        <div className="mb-5 flex flex-col gap-3">
          <Notice tone="warning">The marketplace blocked Shelfcraft’s automatic read of this product page, so only its ID was saved. Finish the import from your own browser:</Notice>
          <BrowserPageImport compact productId={p.id} pageUrl={p.source_url} onDone={refresh} />
        </div>
      )}
      {!p ? <Skeleton className="h-96" /> : (
        <Tabs value={tab} onValueChange={setTab} tabs={[
          { value: "details", label: "Details" }, { value: "images", label: "Images", count: p.images.filter((i) => i.role !== "cutout").length },
          { value: "variants", label: "Variants", count: p.variants?.length ?? 0 }, { value: "reviews", label: "Reviews" }, { value: "competitors", label: "Competitors" },
          { value: "intelligence", label: "Intelligence" }, { value: "creatives", label: "Creatives" },
        ]}>
          <TabPanel value="details"><DetailsTab key={p.updated_at} product={p} onSaved={refresh} /></TabPanel>
          <TabPanel value="images"><ImagesTab product={p} onChange={refresh} /></TabPanel>
          <TabPanel value="variants"><VariantsTab product={p} onSaved={refresh} /></TabPanel>
          <TabPanel value="reviews"><ProductReviews product={p} /></TabPanel>
          <TabPanel value="competitors"><ProductCompetitors product={p} /></TabPanel>
          <TabPanel value="intelligence"><IntelligenceTab product={p} /></TabPanel>
          <TabPanel value="creatives"><CreativesTab productId={p.id} /></TabPanel>
        </Tabs>
      )}
      <Confirm open={confirm} onOpenChange={setConfirm} title="Delete this product?" body="Its generated creatives remain in your asset library."
        onConfirm={async () => { await del(`/products/${id}`); refresh(); toast.success("Product deleted"); router.push("/products"); }} />
    </>
  );
}

function DetailsTab({ product, onSaved }: { product: Product; onSaved: () => void }) {
  const [f, setF] = React.useState(() => ({
    name: product.name, brand_id: product.brand_id ?? "", sku: product.sku ?? "", asin: product.asin ?? "", category: product.category ?? "",
    price: product.price?.toString() ?? "", currency: product.currency, description: product.description ?? "", source_url: product.source_url ?? "",
    features: product.features ?? [], benefits: product.benefits ?? [], tags: (product.tags ?? []).join(", "),
    specs: Object.entries(product.specifications ?? {}).map(([k, v]) => ({ k, v })),
  }));
  const [saving, setSaving] = React.useState(false);
  const set = (k: string, v: unknown) => setF((p) => ({ ...p, [k]: v }));
  const save = async () => {
    setSaving(true);
    try {
      await patch(`/products/${product.id}`, {
        name: f.name, brand_id: f.brand_id || null, sku: f.sku || null, asin: f.asin || null, category: f.category || null,
        price: f.price ? Number(f.price) : null, currency: f.currency || "USD", description: f.description || null, source_url: f.source_url || null,
        features: f.features.map((s) => s.trim()).filter(Boolean), benefits: f.benefits.map((s) => s.trim()).filter(Boolean),
        tags: f.tags.split(",").map((s) => s.trim()).filter(Boolean),
        specifications: Object.fromEntries(f.specs.filter((s) => s.k.trim()).map((s) => [s.k.trim(), s.v])),
      });
      toast.success("Product saved");
      onSaved();
    } catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      <div className="flex flex-col gap-6">
        <Card className="flex flex-col gap-4 p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name *"><Input value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
            <Field label="Brand"><BrandSelect value={f.brand_id} onChange={(v) => set("brand_id", v)} /></Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Category"><Input value={f.category} onChange={(e) => set("category", e.target.value)} /></Field>
            <Field label="SKU"><Input value={f.sku} onChange={(e) => set("sku", e.target.value)} /></Field>
            <Field label="ASIN / ID"><Input value={f.asin} onChange={(e) => set("asin", e.target.value)} /></Field>
            <Field label="Price"><div className="flex gap-1.5"><Input className="w-16" value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} aria-label="Currency" /><Input type="number" min={0} step="0.01" value={f.price} onChange={(e) => set("price", e.target.value)} /></div></Field>
          </div>
          <Field label="Description"><Textarea rows={5} value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
        </Card>
        <Card className="grid gap-6 p-5 md:grid-cols-2">
          <Field label="Features" hint="What the product has or does."><ListInput value={f.features} onChange={(v) => set("features", v)} placeholder="e.g. Double-wall stainless steel" /></Field>
          <Field label="Benefits" hint="What the customer gets."><ListInput value={f.benefits} onChange={(v) => set("benefits", v)} placeholder="e.g. Drinks stay cold for 24 hours" /></Field>
        </Card>
        <Card className="flex flex-col gap-3 p-5">
          <h3 className="text-[13.5px] font-semibold">Specifications</h3>
          {f.specs.map((s, i) => (
            <div key={i} className="flex gap-2">
              <Input className="w-1/3" placeholder="Width" value={s.k} onChange={(e) => set("specs", f.specs.map((x, j) => (j === i ? { ...x, k: e.target.value } : x)))} />
              <Input placeholder="7 cm" value={s.v} onChange={(e) => set("specs", f.specs.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))} />
              <Button variant="ghost" size="icon" aria-label="Remove spec" onClick={() => set("specs", f.specs.filter((_, j) => j !== i))}><X /></Button>
            </div>
          ))}
          <button className="inline-flex w-fit items-center gap-1.5 text-[13px] font-medium text-primary hover:underline" onClick={() => set("specs", [...f.specs, { k: "", v: "" }])}><Plus className="size-3.5" />Add specification</button>
          <p className="text-xs text-muted">Tip: “Width” and “Height” are used automatically by the dimensions infographic.</p>
        </Card>
      </div>
      <div className="flex flex-col gap-4 lg:sticky lg:top-0 lg:self-start">
        <Card className="flex flex-col gap-3 p-4">
          <Button size="lg" onClick={save} loading={saving}>Save changes</Button>
          <Field label="Tags" hint="Comma separated"><Input value={f.tags} onChange={(e) => set("tags", e.target.value)} /></Field>
          <Field label="Source URL"><Input value={f.source_url} onChange={(e) => set("source_url", e.target.value)} placeholder="https://…" /></Field>
        </Card>
      </div>
    </div>
  );
}

function ImagesTab({ product, onChange }: { product: Product; onChange: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const photos = product.images.filter((i) => i.role !== "cutout");
  const cutouts = product.images.filter((i) => i.role === "cutout");
  const onFiles = async (files: File[]) => {
    setBusy(true);
    try { await upload(`/products/${product.id}/images`, files); toast.success(`${files.length} photo${files.length > 1 ? "s" : ""} uploaded`); onChange(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  const makeMain = async (imageId: string) => {
    const order = [imageId, ...photos.map((p) => p.id).filter((x) => x !== imageId)];
    await put(`/products/${product.id}/images/order`, { image_ids: order });
    onChange();
  };
  return (
    <div className="flex flex-col gap-6">
      <Dropzone onFiles={onFiles} label={busy ? "Uploading…" : "Drop product photos here"} hint="JPG, PNG or WebP up to 25 MB · max 12 at a time" disabled={busy} />
      {photos.length === 0 ? <Notice tone="warning">No photos yet. Most creatives use your real photo (cut out locally) so the product is never altered.</Notice> : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
          {photos.map((im) => (
            <div key={im.id} className="flex flex-col gap-1.5">
              <ImageThumb src={im.thumb_url} alt="Product photo" className="aspect-square" onRemove={async () => { await del(`/products/${product.id}/images/${im.id}`); onChange(); }} />
              <div className="flex items-center justify-between">
                {im.role === "main" ? <Badge tone="primary"><Crown />Main</Badge> : <button className="text-xs font-medium text-primary hover:underline" onClick={() => makeMain(im.id)}>Set as main</button>}
                <span className="text-[11px] text-muted">{im.width}×{im.height}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {cutouts.length > 0 && (
        <div>
          <h3 className="mb-2 text-[13.5px] font-semibold">Background-removed cut-outs <span className="font-normal text-muted">· created automatically by rembg (local)</span></h3>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">{cutouts.map((c) => <ImageThumb key={c.id} src={c.thumb_url} alt="Cut-out" className="checkerboard aspect-square [&_img]:object-contain" />)}</div>
        </div>
      )}
    </div>
  );
}

function VariantsTab({ product, onSaved }: { product: Product; onSaved: () => void }) {
  const [rows, setRows] = React.useState<(Variant & { attrText: string; hex: string })[]>(() =>
    (product.variants ?? []).map((v) => ({ ...v, hex: v.attributes.hex ?? "", attrText: Object.entries(v.attributes).filter(([k]) => k !== "hex").map(([k, val]) => `${k}: ${val}`).join(", ") })));
  const [saving, setSaving] = React.useState(false);
  const save = async () => {
    setSaving(true);
    try {
      const variants = rows.filter((r) => r.name.trim()).map((r) => {
        const attributes: Record<string, string> = {};
        r.attrText.split(",").forEach((pair) => { const [k, ...v] = pair.split(":"); if (k?.trim() && v.length) attributes[k.trim()] = v.join(":").trim(); });
        if (r.hex) attributes.hex = r.hex;
        return { id: r.id, name: r.name, sku: r.sku || null, price: r.price ?? null, attributes };
      });
      await patch(`/products/${product.id}`, { variants });
      toast.success("Variants saved");
      onSaved();
    } catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };
  return (
    <Card className="p-5">
      <p className="mb-4 text-[13px] text-muted">Variants can be generated in bulk from the Factory. A variant color is applied with a hue-shift (non-AI) when set.</p>
      <div className="flex flex-col gap-2">
        {rows.length > 0 && <div className="hidden grid-cols-[1.2fr_1fr_1.6fr_90px_70px_36px] gap-2 px-1 text-xs text-muted sm:grid"><span>Name</span><span>SKU</span><span>Attributes (key: value, …)</span><span>Price</span><span>Color</span><span /></div>}
        {rows.map((r, i) => {
          const up = (k: string, v: unknown) => setRows((p) => p.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
          return (
            <div key={i} className="grid grid-cols-2 gap-2 sm:grid-cols-[1.2fr_1fr_1.6fr_90px_70px_36px]">
              <Input value={r.name} placeholder="Forest green" onChange={(e) => up("name", e.target.value)} aria-label="Variant name" />
              <Input value={r.sku ?? ""} placeholder="SKU" onChange={(e) => up("sku", e.target.value)} aria-label="Variant SKU" />
              <Input value={r.attrText} placeholder="size: 750 ml" onChange={(e) => up("attrText", e.target.value)} aria-label="Attributes" />
              <Input type="number" value={r.price ?? ""} onChange={(e) => up("price", e.target.value ? Number(e.target.value) : null)} aria-label="Variant price" />
              <input type="color" value={r.hex || "#888888"} onChange={(e) => up("hex", e.target.value)} className="h-9 w-full cursor-pointer rounded-[10px] border border-border-strong" aria-label="Variant color" />
              <Button variant="ghost" size="icon" aria-label="Remove variant" onClick={() => setRows((p) => p.filter((_, j) => j !== i))}><X /></Button>
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <Button variant="outline" size="sm" onClick={() => setRows((p) => [...p, { name: "", attributes: {}, attrText: "", hex: "" }])}><Plus />Add variant</Button>
        <Button onClick={save} loading={saving}>Save variants</Button>
      </div>
    </Card>
  );
}

interface Research {
  id: string; provider: string; model: string; created_at: string; inputs: Record<string, unknown>;
  result: {
    summary?: string; target_audience?: string; positioning?: string; usps?: string[]; pain_points?: string[];
    features?: { feature: string; explanation: string }[]; benefits?: { benefit: string; from_feature?: string }[];
    personas?: { name: string; description?: string; goals?: string[]; pain_points?: string[] }[];
    competitor_comparison?: { competitor: string; their_strength?: string; our_advantage?: string; gap?: string }[];
    review_sentiment?: { positive_themes?: string[]; negative_themes?: string[]; overall?: string };
    objections?: { objection: string; response: string }[]; marketing_angles?: { angle: string; hook?: string; best_for?: string }[];
    creative_strategy?: Record<string, string | string[]>; assumptions?: string[];
  };
}

function IntelligenceTab({ product }: { product: Product }) {
  const caps = useCapabilities();
  const list = useApi<Research[]>(["research", product.id], `/products/${product.id}/research`);
  const [reviews, setReviews] = React.useState("");
  const [competitors, setCompetitors] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [jobId, setJobId] = React.useState<string | null>(null);
  const run = async () => {
    try { const j = await post<Job>(`/products/${product.id}/research`, { reviews, competitors, notes }); setJobId(j.id); }
    catch (e) { toast.error((e as Error).message); }
  };
  const r = list.data?.[0];
  return (
    <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
      <Card className="flex flex-col gap-4 p-5 lg:sticky lg:top-0 lg:self-start">
        <h3 className="text-[15px] font-semibold">Run product research</h3>
        <p className="text-[13px] text-muted">Analysis uses only your product details plus anything you paste below. Inferences are listed separately as assumptions.</p>
        <Field label="Customer reviews" hint="Leave empty to use the counted analysis from the Reviews tab, or paste a few reviews here."><Textarea rows={4} value={reviews} onChange={(e) => setReviews(e.target.value)} placeholder="“Keeps my coffee hot all morning…”" /></Field>
        <Field label="Competitors" hint="Names, claims, prices — your own notes."><Textarea rows={3} value={competitors} onChange={(e) => setCompetitors(e.target.value)} /></Field>
        <Field label="Notes"><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Launch in Germany; gift angle" /></Field>
        <Button variant="ai" onClick={run} disabled={caps.data?.text_ai === false}><Sparkles />Analyze product</Button>
        {caps.data?.text_ai === false && <Notice tone="warning">No text AI is reachable. Start Ollama or add a free key in <Link href="/settings" className="underline">Settings</Link>.</Notice>}
        {jobId && <JobCard jobId={jobId} onDone={() => list.refetch()} />}
      </Card>
      <div className="flex flex-col gap-4">
        {list.isLoading ? <Skeleton className="h-96" /> : !r ? (
          <EmptyState icon={<Lightbulb />} title="No research yet" body="Get personas, positioning, USPs, objections and marketing angles grounded in your product data." />
        ) : (<>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted"><ProviderBadge provider={r.provider} model={r.model} ai /><span>· {timeAgo(r.created_at)}</span>
            <span>· used: {(r.inputs.used_product_fields as string[] | undefined)?.join(", ") || "name only"}{Number(r.inputs.reviews_chars) ? ", reviews" : ""}{Number(r.inputs.competitors_chars) ? ", competitor notes" : ""}</span></div>
          {r.result.summary && <Card className="p-5"><p className="text-[14px] leading-relaxed">{r.result.summary}</p></Card>}
          <div className="grid gap-4 md:grid-cols-2">
            <Section icon={<Target />} title="Positioning">{r.result.positioning}<div className="mt-2 text-muted">{r.result.target_audience}</div></Section>
            <Section icon={<Crown />} title="Unique selling points"><Bullets items={r.result.usps} /></Section>
            <Section icon={<Users />} title="Personas">
              {r.result.personas?.map((p) => <div key={p.name} className="mb-2"><div className="font-medium">{p.name}</div><div className="text-muted">{p.description}</div></div>)}
            </Section>
            <Section icon={<ShieldQuestion />} title="Objections & answers">
              {r.result.objections?.map((o) => <div key={o.objection} className="mb-2"><div className="font-medium">{o.objection}</div><div className="text-muted">{o.response}</div></div>)}
            </Section>
            <Section icon={<TrendingUp />} title="Marketing angles">
              {r.result.marketing_angles?.map((a) => <div key={a.angle} className="mb-2"><div className="font-medium">{a.angle}</div>{a.hook && <div className="italic text-muted">“{a.hook}”</div>}</div>)}
            </Section>
            <Section icon={<MessageSquareQuote />} title={`Review sentiment · ${r.result.review_sentiment?.overall ?? "no data"}`}>
              {r.result.review_sentiment?.positive_themes?.length ? <><div className="text-xs font-medium text-success">Positive</div><Bullets items={r.result.review_sentiment.positive_themes} /></> : null}
              {r.result.review_sentiment?.negative_themes?.length ? <><div className="mt-2 text-xs font-medium text-danger">Negative</div><Bullets items={r.result.review_sentiment.negative_themes} /></> : null}
              {!r.result.review_sentiment?.positive_themes?.length && !r.result.review_sentiment?.negative_themes?.length && <span className="text-muted">Collect and analyse reviews in the Reviews tab, then run research again.</span>}
            </Section>
            <Section icon={<Lightbulb />} title="Pain points"><Bullets items={r.result.pain_points} /></Section>
            {!!r.result.competitor_comparison?.length && (
              <Section icon={<Users />} title="Competitor gaps">
                {r.result.competitor_comparison.map((c) => <div key={c.competitor} className="mb-2"><div className="font-medium">{c.competitor}</div><div className="text-muted">Ours: {c.our_advantage} · Gap: {c.gap}</div></div>)}
              </Section>
            )}
          </div>
          {!!r.result.assumptions?.length && <Notice tone="warning"><div className="font-medium">Assumptions the model made (verify these)</div><Bullets items={r.result.assumptions} /></Notice>}
        </>)}
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return <Card className="p-4 text-[13px] leading-relaxed"><div className="mb-2 flex items-center gap-2 font-semibold [&_svg]:size-4 [&_svg]:text-primary">{icon}{title}</div>{children}</Card>;
}
function Bullets({ items }: { items?: string[] }) {
  if (!items?.length) return <span className="text-muted">—</span>;
  return <ul className="list-disc space-y-1 pl-4">{items.map((i) => <li key={i}>{i}</li>)}</ul>;
}

function CreativesTab({ productId }: { productId: string }) {
  const q = useApi<{ items: Asset[] }>(["assets", "product", productId], `/assets?product_id=${productId}&kind=image&limit=120`);
  const items = q.data?.items.filter((a) => a.source !== "upload") ?? [];
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (!items.length) return <EmptyState icon={<Sparkles />} title="No creatives for this product yet" body="Generate a listing image set, lifestyle shots or infographics." action={<Link href={`/studio?product=${productId}`}><Button variant="ai"><Sparkles />Open image studio</Button></Link>} />;
  return <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">{items.map((a) => <AssetResult key={a.id} asset={a} />)}</div>;
}
