"use client";
import { Monitor, RectangleVertical, Square } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { QuickAddProduct } from "@/components/quick-add-product";
import { ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Card, Notice, OptionCard, PageHeader } from "@/components/ui/misc";
import { post } from "@/lib/api";

const FORMATS = [
  { aspect: "16:9", title: "Listing video", description: "16:9 · Amazon / Shopify product video", icon: <Monitor /> },
  { aspect: "9:16", title: "Reel / Story", description: "9:16 · Instagram, TikTok", icon: <RectangleVertical /> },
  { aspect: "1:1", title: "Square", description: "1:1 · feed posts", icon: <Square /> },
  { aspect: "4:5", title: "Portrait", description: "4:5 · feed ads", icon: <RectangleVertical /> },
];

function NewVideo() {
  const sp = useSearchParams();
  const router = useRouter();
  const [name, setName] = React.useState("Product video");
  const [productId, setProductId] = React.useState(sp.get("product") ?? "");
  const [aspect, setAspect] = React.useState("16:9");
  const [duration, setDuration] = React.useState(15);
  const [busy, setBusy] = React.useState(false);
  const create = async () => {
    setBusy(true);
    try {
      const r = await post<{ id: string }>("/videos", { name, product_id: productId || null, aspect, target_duration: duration });
      router.push(`/videos/${r.id}`);
    } catch (e) { toast.error((e as Error).message); setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow={<Link href="/videos" className="hover:text-foreground">Video creator</Link>} title="New video" />
      <div className="flex flex-col gap-6">
        <div className="grid gap-3 sm:grid-cols-2">{FORMATS.map((f) => <OptionCard key={f.aspect} icon={f.icon} title={f.title} description={f.description} selected={aspect === f.aspect} onClick={() => setAspect(f.aspect)} />)}</div>
        <Card className="grid gap-4 p-5 sm:grid-cols-3">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Product" hint="Photos & creatives become scenes" aside={<QuickAddProduct label="New" onCreated={setProductId} />}><ProductSelect value={productId} onChange={setProductId} allowNone /></Field>
          <Field label="Target duration"><Select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>{[6, 10, 15, 20, 30, 45, 60].map((s) => <option key={s} value={s}>{s} seconds</option>)}</Select></Field>
        </Card>
        <Notice>Talking-avatar UGC and 360° spins need generative video models that don&apos;t run on this computer for free — they&apos;re not offered rather than faked.</Notice>
        <div className="flex justify-end gap-2"><Link href="/videos"><Button variant="ghost">Cancel</Button></Link><Button size="lg" onClick={create} loading={busy}>Create storyboard</Button></div>
      </div>
    </div>
  );
}

export default function Page() {
  return <React.Suspense><NewVideo /></React.Suspense>;
}
