"use client";
import { Check, LayoutTemplate, Monitor, Smartphone } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { QuickAddProduct } from "@/components/quick-add-product";
import { BrandSelect, ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { Card, Notice, OptionCard, PageHeader } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useActiveBrand, useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Library { modules: Record<string, { label: string; basic: number[]; premium: number[]; mobile: number[] }>; note: string }

function NewAplus() {
  const sp = useSearchParams();
  const router = useRouter();
  const { brand } = useActiveBrand();
  const lib = useApi<Library>(["aplus-modules"], "/aplus/modules");
  const [name, setName] = React.useState("A+ layout");
  const [productId, setProductId] = React.useState(sp.get("product") ?? "");
  const [brandId, setBrandId] = React.useState("");
  const [tier, setTier] = React.useState<"basic" | "premium" | "mobile">((["basic", "premium", "mobile"].includes(sp.get("tier") ?? "") ? sp.get("tier") : "premium") as "premium");
  const mode = sp.get("mode");
  const [mods, setMods] = React.useState<string[]>(mode === "seamless" ? ["seamless"] : mode === "single" ? ["hero_banner"] : ["hero_banner", "feature_row", "comparison", "brand_story"]);
  const [busy, setBusy] = React.useState(false);
  React.useEffect(() => { if (brand && !brandId) setBrandId(brand.id); }, [brand, brandId]);
  const toggle = (k: string) => setMods((m) => (m.includes(k) ? m.filter((x) => x !== k) : m.length >= 7 ? m : [...m, k]));
  const create = async () => {
    if (!mods.length) return toast.error("Choose at least one module.");
    setBusy(true);
    try {
      const r = await post<{ id: string }>("/aplus", { name, product_id: productId || null, brand_id: brandId || null, tier, modules: mods });
      router.push(`/aplus/${r.id}`);
    } catch (e) { toast.error((e as Error).message); setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow={<Link href="/aplus" className="hover:text-foreground">A+ content</Link>} title="New A+ layout" description="Modules are filled with your product copy, photos and brand styling — then everything stays editable." />
      <div className="flex flex-col gap-6">
        <Card className="grid gap-4 p-5 sm:grid-cols-3">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Product" aside={<QuickAddProduct label="New" onCreated={setProductId} />}><ProductSelect value={productId} onChange={setProductId} allowNone /></Field>
          <Field label="Brand"><BrandSelect value={brandId} onChange={setBrandId} /></Field>
        </Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <OptionCard icon={<Monitor />} title="Premium" description="Full-width desktop modules" selected={tier === "premium"} onClick={() => setTier("premium")} />
          <OptionCard icon={<LayoutTemplate />} title="Basic" description="970-wide standard modules" selected={tier === "basic"} onClick={() => setTier("basic")} />
          <OptionCard icon={<Smartphone />} title="Premium mobile" description="Mobile-optimized modules" selected={tier === "mobile"} onClick={() => setTier("mobile")} />
        </div>
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between"><h3 className="text-[14px] font-semibold">Modules</h3><span className="text-xs text-muted">{mods.length}/7 selected · order can be changed later</span></div>
          <div className="grid gap-2 sm:grid-cols-2">
            {lib.data && Object.entries(lib.data.modules).map(([k, m]) => {
              const on = mods.includes(k);
              return (
                <button key={k} onClick={() => toggle(k)} className={cn("flex items-center gap-3 rounded-[12px] border px-3 py-2.5 text-left", on ? "border-primary bg-primary-soft" : "border-border hover:bg-sunken")}>
                  <span className={cn("flex size-5 items-center justify-center rounded-[6px] border", on ? "border-primary bg-primary text-white" : "border-border-strong")}>{on && <Check className="size-3.5" />}</span>
                  <span className="flex-1 text-[13px] font-medium">{m.label}</span>
                  <span className="font-mono text-[11px] text-muted">{m[tier][0]}×{m[tier][1]}</span>
                  {on && <span className="text-[11px] text-primary">#{mods.indexOf(k) + 1}</span>}
                </button>
              );
            })}
          </div>
          {lib.data && <Notice className="mt-4 text-xs">{lib.data.note}</Notice>}
        </Card>
        <div className="flex justify-end gap-2"><Link href="/aplus"><Button variant="ghost">Cancel</Button></Link><Button size="lg" onClick={create} loading={busy}>Create layout</Button></div>
      </div>
    </div>
  );
}

export default function Page() {
  return <React.Suspense><NewAplus /></React.Suspense>;
}
