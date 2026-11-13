"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { ImageThumb } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { Field, Input, ListInput, Textarea } from "@/components/ui/form";
import { Notice } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { post, upload } from "@/lib/api";
import { useActiveBrand } from "@/lib/hooks";
import type { Product } from "@/lib/types";

/** "+ New product" button that creates a product in a dialog and hands back its id (used next to product pickers). */
export function QuickAddProduct({ onCreated, label = "New product" }: { onCreated: (id: string) => void; label?: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
        <Plus className="size-3.5" />{label}
      </button>
      <QuickAddProductDialog open={open} onOpenChange={setOpen} onCreated={onCreated} />
    </>
  );
}

export function QuickAddProductDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (id: string) => void }) {
  const qc = useQueryClient();
  const { brand } = useActiveBrand();
  const [files, setFiles] = React.useState<File[]>([]);
  const [f, setF] = React.useState({ name: "", category: "", price: "", description: "" });
  const [features, setFeatures] = React.useState<string[]>([""]);
  const [saving, setSaving] = React.useState(false);
  const previews = React.useMemo(() => files.map((x) => URL.createObjectURL(x)), [files]);
  React.useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);
  const reset = () => { setFiles([]); setF({ name: "", category: "", price: "", description: "" }); setFeatures([""]); };

  const save = async () => {
    if (!f.name.trim()) return toast.error("Product name is required.");
    setSaving(true);
    try {
      const p = await post<Product>("/products", {
        name: f.name.trim(), category: f.category || null, description: f.description || null, price: f.price ? Number(f.price) : null,
        features: features.map((s) => s.trim()).filter(Boolean), brand_id: brand?.id ?? null,
      });
      if (files.length) await upload(`/products/${p.id}/images`, files);
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success(`“${p.name}” added and selected`);
      onCreated(p.id);
      reset();
      onOpenChange(false);
    } catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Add a new product" description="The more detail you give, the better the AI copy. You can add more later on the product page."
      footer={<><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={save} loading={saving}>Add & select</Button></>}>
      <div className="flex flex-col gap-4">
        <Field label="Photos" hint="Recommended — your real photo is used as-is in images. Plain backgrounds cut out best.">
          <Dropzone compact onFiles={(x) => setFiles((p) => [...p, ...x].slice(0, 12))} label="Add product photos" />
          {files.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{files.map((x, i) => <ImageThumb key={i} src={previews[i]} alt={x.name} className="size-14" onRemove={() => setFiles((p) => p.filter((_, j) => j !== i))} />)}</div>}
        </Field>
        <Field label="Name *"><Input autoFocus value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Bamboo Cutting Board, Large" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category"><Input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} placeholder="Kitchen" /></Field>
          <Field label="Price"><Input type="number" min={0} step="0.01" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field>
        </div>
        <Field label="Description"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="What it is, materials, size, who it's for" /></Field>
        <Field label="Key features" hint="Facts only — the AI won't invent features you don't list."><ListInput value={features} onChange={setFeatures} placeholder="e.g. Organic bamboo, juice groove" max={10} /></Field>
        {brand && <Notice>Will be added to <b>{brand.name}</b>.</Notice>}
      </div>
    </Dialog>
  );
}
