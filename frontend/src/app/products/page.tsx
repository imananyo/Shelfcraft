"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, Globe, LayoutGrid, List, Package, Plus, Search, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { BrandSelect, ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Badge, Card, EmptyState, ErrorState, Notice, PageHeader, Skeleton } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { download, post, upload } from "@/lib/api";
import { useActiveBrand, useApi } from "@/lib/hooks";
import type { Product } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

export default function ProductsPage() {
  const [q, setQ] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [brandId, setBrandId] = React.useState("");
  const [sort, setSort] = React.useState("updated");
  const [view, setView] = React.useState<"grid" | "list">("grid");
  const [adding, setAdding] = React.useState(false);
  const [importing, setImporting] = React.useState(false);
  React.useEffect(() => { const t = setTimeout(() => setDebounced(q), 200); return () => clearTimeout(t); }, [q]);
  const params = new URLSearchParams({ sort });
  if (debounced) params.set("q", debounced);
  if (category) params.set("category", category);
  if (brandId) params.set("brand_id", brandId);
  const list = useApi<{ items: Product[]; categories: string[] }>(["products", params.toString()], `/products?${params}`);

  return (
    <>
      <PageHeader title="Products" description={list.data ? `${list.data.items.length} product${list.data.items.length === 1 ? "" : "s"} in your catalog` : "Your product catalog"}
        actions={<>
          <Button variant="outline" onClick={() => setImporting(true)}><Upload />Import CSV</Button>
          <Button variant="outline" onClick={() => download("/products/export.csv", {}, "products.csv").catch((e) => toast.error(e.message))}><Download />Export CSV</Button>
          <Button onClick={() => setAdding(true)}><Plus />Add product</Button>
        </>} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input className="pl-9" placeholder="Search name, SKU, ASIN, category…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <Select className="w-44" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category"><option value="">All categories</option>{list.data?.categories.map((c) => <option key={c}>{c}</option>)}</Select>
        <BrandSelect className="w-44" value={brandId} onChange={setBrandId} />
        <Select className="w-40" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort"><option value="updated">Recently updated</option><option value="created">Newest</option><option value="name">Name A–Z</option><option value="price">Price</option></Select>
        <div className="flex rounded-[10px] border border-border-strong p-0.5">
          {(["grid", "list"] as const).map((v) => <button key={v} aria-label={`${v} view`} onClick={() => setView(v)} className={cn("flex size-8 items-center justify-center rounded-[8px] text-muted", view === v && "bg-sunken text-foreground")}>{v === "grid" ? <LayoutGrid className="size-4" /> : <List className="size-4" />}</button>)}
        </div>
      </div>
      {list.error && <ErrorState error={list.error} onRetry={() => list.refetch()} />}
      {list.isLoading ? <div className="grid grid-cols-2 gap-4 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-60" />)}</div>
        : list.data?.items.length === 0 ? (
          debounced || category || brandId ? <EmptyState icon={<Search />} title="No matching products" body="Try a different search or clear filters." action={<Button variant="outline" onClick={() => { setQ(""); setCategory(""); setBrandId(""); }}>Clear filters</Button>} />
            : <EmptyState icon={<Package />} title="Add your first product" body="Upload product photos and details — they power every listing, image and video." action={<Button onClick={() => setAdding(true)}><Plus />Add product</Button>} />
        ) : view === "grid" ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {list.data?.items.map((p) => (
              <Link key={p.id} href={`/products/${p.id}`}>
                <Card className="group overflow-hidden transition hover:border-border-strong">
                  <ImageThumb src={p.cover_url} alt={p.name} className="aspect-square rounded-none border-0" />
                  <div className="p-3">
                    <div className="truncate text-[13.5px] font-semibold">{p.name}</div>
                    <div className="mt-0.5 flex items-center justify-between text-xs text-muted">
                      <span className="truncate">{p.category ?? "Uncategorized"}{p.sku ? ` · ${p.sku}` : ""}</span>
                      {p.price != null && <span className="tabular-nums text-foreground">{p.currency} {p.price.toFixed(2)}</span>}
                    </div>
                    <div className="mt-2 flex gap-1.5">{p.brand_name && <Badge>{p.brand_name}</Badge>}{!p.image_count && <Badge tone="warning">No photo</Badge>}{p.variant_count > 0 && <Badge>{p.variant_count} variants</Badge>}</div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <Card className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="border-b border-border text-left text-xs text-muted"><tr><th className="px-4 py-2.5 font-medium">Product</th><th className="px-3 font-medium">SKU</th><th className="px-3 font-medium">Category</th><th className="px-3 font-medium">Brand</th><th className="px-3 text-right font-medium">Price</th><th className="px-4 text-right font-medium">Updated</th></tr></thead>
              <tbody>
                {list.data?.items.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0 hover:bg-sunken/60">
                    <td className="px-4 py-2"><Link href={`/products/${p.id}`} className="flex items-center gap-3 font-medium"><ImageThumb src={p.cover_url} alt={p.name} className="size-9" />{p.name}</Link></td>
                    <td className="px-3 font-mono text-xs">{p.sku ?? "—"}</td><td className="px-3">{p.category ?? "—"}</td><td className="px-3">{p.brand_name ?? "—"}</td>
                    <td className="px-3 text-right tabular-nums">{p.price != null ? `${p.currency} ${p.price.toFixed(2)}` : "—"}</td>
                    <td className="px-4 text-right text-muted">{timeAgo(p.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      <AddProductDialog open={adding} onOpenChange={setAdding} />
      <ImportDialog open={importing} onOpenChange={setImporting} />
    </>
  );
}

function AddProductDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { brand } = useActiveBrand();
  const [step, setStep] = React.useState<"source" | "details">("source");
  const [url, setUrl] = React.useState("");
  const [fetching, setFetching] = React.useState(false);
  const [files, setFiles] = React.useState<File[]>([]);
  const [form, setForm] = React.useState({ name: "", category: "", description: "", price: "", sku: "", source_url: "" });
  const [saving, setSaving] = React.useState(false);
  const previews = React.useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  React.useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);
  React.useEffect(() => { if (!open) { setStep("source"); setFiles([]); setUrl(""); setForm({ name: "", category: "", description: "", price: "", sku: "", source_url: "" }); } }, [open]);

  const fetchUrl = async () => {
    setFetching(true);
    try {
      const r = await post<{ ok: boolean; error?: string; suggestions: { name?: string; description?: string; price?: number; source_url?: string } }>("/products/fetch-url", { url });
      if (!r.ok) { toast.error(r.error ?? "Couldn't read that page"); return; }
      setForm((f) => ({ ...f, name: r.suggestions.name ?? f.name, description: r.suggestions.description ?? f.description,
        price: r.suggestions.price != null ? String(r.suggestions.price) : f.price, source_url: r.suggestions.source_url ?? url }));
      setStep("details");
      toast.success("Details filled from the page — review them and add your photos.");
    } catch (e) { toast.error((e as Error).message); } finally { setFetching(false); }
  };

  const save = async () => {
    if (!form.name.trim()) return toast.error("Product name is required.");
    setSaving(true);
    try {
      const p = await post<Product>("/products", { name: form.name, category: form.category || null, description: form.description || null, sku: form.sku || null,
        price: form.price ? Number(form.price) : null, source_url: form.source_url || null, brand_id: brand?.id ?? null });
      if (files.length) await upload(`/products/${p.id}/images`, files);
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Product added");
      onOpenChange(false);
      router.push(`/products/${p.id}`);
    } catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Add product" description={step === "source" ? "Start from a public product page, or enter details yourself." : "Photos matter most — they're used as-is in your creatives."}
      footer={step === "details" ? <><Button variant="ghost" onClick={() => setStep("source")}>Back</Button><Button onClick={save} loading={saving}>Add product</Button></> : undefined}>
      {step === "source" ? (
        <div className="flex flex-col gap-4">
          <Field label="Product page URL" hint="Reads public metadata from your own store or other permitted pages. Amazon & Walmart block automated access — enter those details manually.">
            <div className="flex gap-2">
              <div className="relative flex-1"><Globe className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input className="pl-9" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourstore.com/products/…" /></div>
              <Button variant="outline" onClick={fetchUrl} loading={fetching} disabled={!url.trim()}>Fetch</Button>
            </div>
          </Field>
          <div className="flex items-center gap-3 text-xs text-muted"><div className="h-px flex-1 bg-border" />or<div className="h-px flex-1 bg-border" /></div>
          <Button variant="secondary" size="lg" onClick={() => setStep("details")}><Plus />Enter details manually</Button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <Field label="Photos" hint="Clear shots on a plain background give the best cut-outs. First photo becomes the main image.">
            <Dropzone compact onFiles={(f) => setFiles((p) => [...p, ...f].slice(0, 12))} label="Add product photos" />
            {files.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{files.map((f, i) => <ImageThumb key={i} src={previews[i]} alt={f.name} className="size-16" onRemove={() => setFiles((p) => p.filter((_, j) => j !== i))} />)}</div>}
          </Field>
          <Field label="Name *"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Insulated Steel Bottle 750 ml" /></Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Category"><Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Kitchen" /></Field>
            <Field label="SKU"><Input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} /></Field>
            <Field label="Price"><Input type="number" min={0} step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></Field>
          </div>
          <Field label="Description"><Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="What it is, what it's made of, who it's for" /></Field>
          {brand && <Notice>Will be added to <b>{brand.name}</b>.</Notice>}
        </div>
      )}
    </Dialog>
  );
}

function ImportDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const [result, setResult] = React.useState<{ created: number; updated: number; errors: { line: number; error: string }[] } | null>(null);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (!open) setResult(null); }, [open]);
  const onFiles = async (files: File[]) => {
    setBusy(true);
    try {
      const r = await upload<typeof result>("/products/import.csv", files[0], "file");
      setResult(r);
      qc.invalidateQueries({ queryKey: ["products"] });
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Import products from CSV" description="Rows with an existing SKU update that product; others are created.">
      <div className="flex flex-col gap-4">
        <Dropzone onFiles={onFiles} multiple={false} accept=".csv,text/csv" label={busy ? "Importing…" : "Drop a CSV file"} hint="UTF-8, header row required" disabled={busy} />
        <div className="rounded-[10px] bg-sunken p-3 font-mono text-[11.5px] leading-relaxed text-muted">
          name, sku, asin, brand, category, price, currency, description,<br />features (a | b | c), benefits (a | b), specifications (JSON), tags (a, b), source_url
        </div>
        <button className="inline-flex w-fit items-center gap-1.5 text-[13px] font-medium text-primary hover:underline"
          onClick={() => { const blob = new Blob(["name,sku,category,price,features,benefits\nExample Bottle,EX-1,Kitchen,19.99,Double-wall steel|Leakproof lid,Cold for 24h|No spills\n"], { type: "text/csv" }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "shelfcraft-template.csv"; a.click(); }}>
          <FileSpreadsheet className="size-4" />Download template
        </button>
        {result && (
          <Notice tone={result.errors.length ? "warning" : "success"}>
            Created {result.created}, updated {result.updated}{result.errors.length ? `, ${result.errors.length} row(s) skipped:` : "."}
            {result.errors.slice(0, 5).map((e) => <div key={e.line} className="text-xs">Line {e.line}: {e.error}</div>)}
          </Notice>
        )}
      </div>
    </Dialog>
  );
}
