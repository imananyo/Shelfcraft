"use client";
import { Check, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { QuickAddProduct } from "@/components/quick-add-product";
import { ImageThumb, ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form";
import { Card, Notice, PageHeader, TabPanel, Tabs } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Product } from "@/lib/types";
import { cn } from "@/lib/utils";

const MK = [["amazon", "Amazon"], ["amazon_mobile", "Amazon Mobile"], ["shopify", "Shopify"], ["walmart", "Walmart"], ["tiktok", "TikTok Shop"]];

export default function TitleBullets() {
  const router = useRouter();
  const products = useApi<{ items: Product[] }>(["products", "tb"], "/products?limit=500&sort=name");
  const langs = useApi<Record<string, string>>(["languages"], "/languages");
  const [tab, setTab] = React.useState("single");
  const [productId, setProductId] = React.useState("");
  const [sel, setSel] = React.useState<string[]>([]);
  const [mk, setMk] = React.useState("amazon");
  const [lang, setLang] = React.useState("en");
  const [busy, setBusy] = React.useState(false);
  const single = async () => {
    setBusy(true);
    try { const r = await post<{ id: string }>("/listings", { product_id: productId, marketplace: mk, language: lang }); router.push(`/listings/${r.id}`); }
    catch (e) { toast.error((e as Error).message); setBusy(false); }
  };
  const bulk = async () => {
    setBusy(true);
    try { const r = await post<{ batch_id: string; total: number }>("/listings/bulk", { product_ids: sel, marketplace: mk, language: lang }); toast.success(`Writing ${r.total} listings`); router.push(`/factory?run=${r.batch_id}`); }
    catch (e) { toast.error((e as Error).message); setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow={<Link href="/labs" className="hover:text-foreground">Labs</Link>} title="Title & Bullets" description="An optimized title, item highlights and 5 bullet points, grounded in your product facts." />
      <Card className="p-5">
        <Tabs value={tab} onValueChange={setTab} tabs={[{ value: "single", label: "Single product" }, { value: "bulk", label: "Bulk run" }]}>
          <div className="mb-4 grid grid-cols-2 gap-3">
            <Field label="Marketplace"><Select value={mk} onChange={(e) => setMk(e.target.value)}>{MK.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
            <Field label="Language"><Select value={lang} onChange={(e) => setLang(e.target.value)}>{langs.data && Object.entries(langs.data).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          </div>
          <TabPanel value="single" className="flex flex-col gap-3">
            <Field label="Product" aside={<QuickAddProduct onCreated={setProductId} />}><ProductSelect value={productId} onChange={setProductId} /></Field>
            <Button variant="ai" size="lg" disabled={!productId} loading={busy} onClick={single}><Sparkles />Generate title & bullets</Button>
          </TabPanel>
          <TabPanel value="bulk" className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-[13px]"><span className="font-medium">Products ({sel.length})</span>
              <button className="text-primary hover:underline" onClick={() => setSel(products.data?.items.map((p) => p.id) ?? [])}>Select all</button></div>
            <div className="grid max-h-72 gap-1 overflow-y-auto sm:grid-cols-2">
              {products.data?.items.map((p) => {
                const on = sel.includes(p.id);
                return (
                  <button key={p.id} onClick={() => setSel((s) => (on ? s.filter((x) => x !== p.id) : [...s, p.id]))}
                    className={cn("flex items-center gap-2 rounded-[9px] border px-2 py-1.5 text-left text-[13px]", on ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                    <span className={cn("flex size-4 items-center justify-center rounded border", on ? "border-primary bg-primary text-white" : "border-border-strong")}>{on && <Check className="size-3" />}</span>
                    <ImageThumb src={p.cover_url} alt="" className="size-7" /><span className="truncate">{p.name}</span>
                  </button>
                );
              })}
            </div>
            <Button variant="ai" size="lg" disabled={!sel.length} loading={busy} onClick={bulk}><Sparkles />Write {sel.length} listings</Button>
            <p className="text-xs text-muted">≈ 2 minutes per listing with the local model. Each result opens as a normal, editable listing.</p>
          </TabPanel>
        </Tabs>
      </Card>
      <Notice className="mt-4 text-xs">Length limits are guidance (Amazon Mobile shows ~80 title characters). Shelfcraft doesn&apos;t claim marketplace compliance — verify current rules before publishing.</Notice>
    </div>
  );
}
