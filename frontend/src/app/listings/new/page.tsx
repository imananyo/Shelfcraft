"use client";
import { Megaphone, ShoppingBag, Sparkles, Store } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { BrandSelect, ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Card, Notice, OptionCard, PageHeader } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useActiveBrand, useCapabilities, useProviders } from "@/lib/hooks";

const MK = [
  { key: "amazon", title: "Amazon", icon: <ShoppingBag /> }, { key: "shopify", title: "Shopify", icon: <Store /> },
  { key: "walmart", title: "Walmart", icon: <Store /> }, { key: "tiktok", title: "TikTok Shop", icon: <Megaphone /> },
];
const COUNTRIES = ["US", "UK", "CA", "DE", "FR", "ES", "IT", "IN", "JP", "AU", "MX", "AE"];
const LANGS = [["en", "English"], ["de", "German"], ["fr", "French"], ["es", "Spanish"], ["it", "Italian"], ["hi", "Hindi"], ["ja", "Japanese"], ["pt", "Portuguese"], ["ar", "Arabic"]];

function NewListing() {
  const sp = useSearchParams();
  const router = useRouter();
  const { brand } = useActiveBrand();
  const caps = useCapabilities();
  const providers = useProviders();
  const [mk, setMk] = React.useState(sp.get("marketplace") ?? "amazon");
  const [productId, setProductId] = React.useState(sp.get("product") ?? "");
  const [brandId, setBrandId] = React.useState("");
  const [o, setO] = React.useState({ country: "US", language: "en", audience: "", tone: "", keywords: "", creative_preferences: "", provider: "" });
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (brand && !brandId) setBrandId(brand.id); }, [brand, brandId]);
  const textProviders = providers.data?.filter((p) => p.kinds.includes("text") && p.state === "available") ?? [];

  const start = async () => {
    if (!productId) return toast.error("Choose a product first.");
    setBusy(true);
    try {
      const r = await post<{ id: string }>("/listings", { product_id: productId, brand_id: brandId || null, marketplace: mk, ...o, provider: o.provider || null });
      router.push(`/listings/${r.id}`);
    } catch (e) { toast.error((e as Error).message); setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow={<Link href="/listings" className="hover:text-foreground">Listing builder</Link>} title="New listing" description="Copy is generated in the background — you can keep working while it runs." />
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{MK.map((m) => <OptionCard key={m.key} icon={m.icon} title={m.title} selected={mk === m.key} onClick={() => setMk(m.key)} className="flex-col items-start" />)}</div>
        <Card className="flex flex-col gap-4 p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Product *" aside={<Link href="/products" className="text-primary hover:underline">Manage</Link>}><ProductSelect value={productId} onChange={setProductId} /></Field>
            <Field label="Brand"><BrandSelect value={brandId} onChange={setBrandId} /></Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Country"><Select value={o.country} onChange={(e) => setO({ ...o, country: e.target.value })}>{COUNTRIES.map((c) => <option key={c}>{c}</option>)}</Select></Field>
            <Field label="Language"><Select value={o.language} onChange={(e) => setO({ ...o, language: e.target.value })}>{LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
            <Field label="Text AI"><Select value={o.provider} onChange={(e) => setO({ ...o, provider: e.target.value })}><option value="">Automatic (free fallback)</option>{textProviders.map((p) => <option key={p.name} value={p.name}>{p.label}</option>)}</Select></Field>
          </div>
          <Field label="Target audience" hint="Optional — overrides the brand profile."><Input value={o.audience} onChange={(e) => setO({ ...o, audience: e.target.value })} placeholder="e.g. Weekend hikers who value durability" /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tone"><Input value={o.tone} onChange={(e) => setO({ ...o, tone: e.target.value })} placeholder="Defaults to brand tone" /></Field>
            <Field label="Seed keywords"><Input value={o.keywords} onChange={(e) => setO({ ...o, keywords: e.target.value })} placeholder="insulated bottle, leakproof" /></Field>
          </div>
          <Field label="Creative preferences"><Textarea rows={2} value={o.creative_preferences} onChange={(e) => setO({ ...o, creative_preferences: e.target.value })} placeholder="Warm outdoor scenes, avoid people's faces…" /></Field>
        </Card>
        {caps.data?.text_ai === false && <Notice tone="warning">No text AI is reachable right now. Start Ollama or add a free key in <Link href="/settings" className="underline">Settings</Link> — your listing will be saved as a draft you can write by hand.</Notice>}
        <div className="flex justify-end gap-2">
          <Link href="/listings"><Button variant="ghost">Cancel</Button></Link>
          <Button variant="ai" size="lg" onClick={start} loading={busy}><Sparkles />Generate listing</Button>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <React.Suspense><NewListing /></React.Suspense>;
}
