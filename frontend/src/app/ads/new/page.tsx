"use client";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { QuickAddProduct } from "@/components/quick-add-product";
import { ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { ChipsInput, Field, Select } from "@/components/ui/form";
import { Card, Notice, OptionCard, PageHeader } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Fmt { label: string; w: number; h: number; kind: string; duration?: number }

function NewAds() {
  const sp = useSearchParams();
  const router = useRouter();
  const formats = useApi<Record<string, Fmt>>(["ad-formats"], "/ads/formats");
  const [format, setFormat] = React.useState(sp.get("format") ?? "sb_image");
  const [productId, setProductId] = React.useState(sp.get("product") ?? "");
  const [count, setCount] = React.useState(6);
  const [personas, setPersonas] = React.useState<string[]>([]);
  const [goal, setGoal] = React.useState("conversions");
  const [busy, setBusy] = React.useState(false);
  const start = async () => {
    if (!productId) return toast.error("Choose a product.");
    setBusy(true);
    try { const r = await post<{ id: string }>("/ads", { product_id: productId, format, count, personas: personas.length ? personas : null, goal }); router.push(`/ads/${r.id}`); }
    catch (e) { toast.error((e as Error).message); setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow={<Link href="/ads" className="hover:text-foreground">Ads studio</Link>} title="New ad set" description="Concepts are brainstormed by your free/local text AI and grounded in your product facts." />
      <div className="flex flex-col gap-6">
        <div className="grid gap-3 sm:grid-cols-2">
          {formats.data && Object.entries(formats.data).map(([k, f]) => (
            <OptionCard key={k} icon={<Sparkles />} title={f.label} description={`${f.w} × ${f.h}${f.duration ? ` · ${f.duration} s video` : ""}`} selected={format === k} onClick={() => setFormat(k)} />
          ))}
        </div>
        <Card className="grid gap-4 p-5 sm:grid-cols-2">
          <Field label="Product *" aside={<QuickAddProduct onCreated={setProductId} />}><ProductSelect value={productId} onChange={setProductId} /></Field>
          <Field label="Goal"><Select value={goal} onChange={(e) => setGoal(e.target.value)}><option value="conversions">Conversions</option><option value="awareness">Awareness</option><option value="consideration">Consideration</option><option value="retargeting">Retargeting</option></Select></Field>
          <Field label="Personas" hint="Leave empty to use personas from Product intelligence." aside="Enter to add" className="sm:col-span-2"><ChipsInput value={personas} onChange={setPersonas} max={4} placeholder="e.g. Weekend hiker" /></Field>
          <Field label="Number of concepts"><Select value={count} onChange={(e) => setCount(Number(e.target.value))}>{[4, 6, 8, 10, 12].map((n) => <option key={n}>{n}</option>)}</Select></Field>
        </Card>
        <Notice className="text-xs">Headlines avoid unverifiable claims. Sizes match commonly documented ad specs — verify in your ad console before launching.</Notice>
        <div className="flex justify-end gap-2"><Link href="/ads"><Button variant="ghost">Cancel</Button></Link><Button variant="ai" size="lg" onClick={start} loading={busy}><Sparkles />Brainstorm concepts</Button></div>
      </div>
    </div>
  );
}

export default function Page() {
  return <React.Suspense><NewAds /></React.Suspense>;
}
