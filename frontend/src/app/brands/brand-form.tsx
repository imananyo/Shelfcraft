"use client";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Globe, Info, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { ChipsInput, ColorSwatches, Field, Input, Select, Textarea } from "@/components/ui/form";
import { Card, Notice } from "@/components/ui/misc";
import { Confirm } from "@/components/ui/overlay";
import { del, patch, post, upload } from "@/lib/api";
import type { Brand } from "@/lib/types";

const FONTS = ["Inter", "Geist", "Manrope", "DM Sans", "Plus Jakarta Sans", "Outfit", "Poppins", "Montserrat", "Lato", "Nunito Sans",
  "Bricolage Grotesque", "Space Grotesk", "Sora", "Playfair Display", "DM Serif Display", "Fraunces", "Libre Baskerville", "Cormorant Garamond", "Archivo", "Work Sans"];
const LANGS = [["en", "English"], ["es", "Spanish"], ["de", "German"], ["fr", "French"], ["it", "Italian"], ["pt", "Portuguese"], ["nl", "Dutch"], ["ja", "Japanese"], ["hi", "Hindi"], ["ar", "Arabic"]];

type Form = Omit<Brand, "id" | "guidelines" | "product_count" | "created_at" | "updated_at" | "logo_url" | "logo_asset_id">;
const EMPTY: Form = { name: "", website: "", colors: [], primary_font: "", secondary_font: "", language: "en", tagline: "", tone_of_voice: "",
  target_audience: "", positioning: "", values: [], aesthetic: [], visual_identity: "", marketing_guidelines: "", extra_details: "" };

export function BrandForm({ brand }: { brand?: Brand }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [f, setF] = React.useState<Form>(() => (brand ? { ...EMPTY, ...Object.fromEntries(Object.entries(brand).map(([k, v]) => [k, v ?? (EMPTY as Record<string, unknown>)[k]])) } as Form : EMPTY));
  const [saving, setSaving] = React.useState(false);
  const [url, setUrl] = React.useState(brand?.website ?? "");
  const [scraping, setScraping] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [dirty, setDirty] = React.useState(false);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => { setF((p) => ({ ...p, [k]: v })); setDirty(true); };

  React.useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const refresh = () => { qc.invalidateQueries({ queryKey: ["brands"] }); qc.invalidateQueries({ queryKey: ["brand"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); };

  const save = async () => {
    if (!f.name.trim()) return toast.error("Give your brand a name.");
    setSaving(true);
    try {
      const body = { ...f, website: url || f.website || null };
      if (brand) { await patch(`/brands/${brand.id}`, body); toast.success("Brand saved"); }
      else { const b = await post<Brand>("/brands", body); toast.success("Brand created"); router.replace(`/brands/${b.id}`); }
      setDirty(false);
      refresh();
    } catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };

  const scrape = async () => {
    if (!url.trim()) return toast.error("Enter your website URL first.");
    setScraping(true);
    try {
      const r = await post<{ ok: boolean; error?: string; suggestions: Partial<Form> & { image_url?: string }; note?: string }>("/brands/autofill", { url });
      if (!r.ok) return toast.error(r.error ?? "Couldn't read that page.");
      const s = r.suggestions;
      setF((p) => ({ ...p, name: p.name || s.name || "", tagline: p.tagline || s.tagline || "", colors: p.colors.length ? p.colors : (s.colors ?? []),
        primary_font: p.primary_font || s.primary_font || "", website: s.website ?? url }));
      setDirty(true);
      toast.success("Filled from your website — review before saving.");
    } catch (e) { toast.error((e as Error).message); } finally { setScraping(false); }
  };

  const onLogo = async (files: File[]) => {
    if (!brand) return toast.message("Save the brand first, then add a logo.");
    try { await upload(`/brands/${brand.id}/logo`, files[0], "file"); toast.success("Logo uploaded"); refresh(); } catch (e) { toast.error((e as Error).message); }
  };
  const onGuide = async (files: File[]) => {
    if (!brand) return toast.message("Save the brand first, then add guideline documents.");
    for (const file of files) {
      try { const r = await upload<{ chars: number }>(`/brands/${brand.id}/guidelines`, file, "file", { title: file.name }); toast.success(`Added ${file.name} (${r.chars.toLocaleString()} characters of text)`); }
      catch (e) { toast.error(`${file.name}: ${(e as Error).message}`); }
    }
    refresh();
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="flex flex-col gap-6">
        <Card className="p-5">
          <Field label="Website" hint="Auto-fill reads only public page metadata (title, description, theme colors, fonts). Nothing is sent to an AI service.">
            <div className="flex gap-2">
              <div className="relative flex-1"><Globe className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input className="pl-9" value={url} onChange={(e) => { setUrl(e.target.value); setDirty(true); }} placeholder="https://yourbrand.com" /></div>
              <Button variant="outline" onClick={scrape} loading={scraping}>Auto-fill</Button>
            </div>
          </Field>
        </Card>

        <Card className="flex flex-col gap-5 p-5">
          <h2 className="text-[15px] font-semibold">Identity</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Brand name *"><Input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Northwind Goods" maxLength={120} /></Field>
            <Field label="Tagline"><Input value={f.tagline ?? ""} onChange={(e) => set("tagline", e.target.value)} placeholder="e.g. Performance meets design" maxLength={200} /></Field>
          </div>
          <Field label="Brand colors" aside="max 6 · first color is primary"><ColorSwatches value={f.colors} onChange={(v) => set("colors", v)} max={6} /></Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Heading font"><Select value={f.primary_font ?? ""} onChange={(e) => set("primary_font", e.target.value)}><option value="">Default (Inter)</option>{FONTS.map((x) => <option key={x}>{x}</option>)}</Select></Field>
            <Field label="Body font"><Select value={f.secondary_font ?? ""} onChange={(e) => set("secondary_font", e.target.value)}><option value="">Same as heading</option>{FONTS.map((x) => <option key={x}>{x}</option>)}</Select></Field>
            <Field label="Language"><Select value={f.language} onChange={(e) => set("language", e.target.value)}>{LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
          </div>
          <Field label="Visual identity" hint="Photography style, composition, props, lighting you prefer."><Textarea value={f.visual_identity ?? ""} onChange={(e) => set("visual_identity", e.target.value)} placeholder="Bright natural light, minimal props, lots of negative space…" /></Field>
          <Field label="Brand aesthetic" aside="Enter to add"><ChipsInput value={f.aesthetic} onChange={(v) => set("aesthetic", v)} placeholder="e.g. Minimalist, Clean" /></Field>
        </Card>

        <Card className="flex flex-col gap-5 p-5">
          <h2 className="text-[15px] font-semibold">Voice & positioning</h2>
          <Field label="Tone of voice"><Input value={f.tone_of_voice ?? ""} onChange={(e) => set("tone_of_voice", e.target.value)} placeholder="e.g. Bold, confident, approachable" /></Field>
          <Field label="Target audience"><Textarea value={f.target_audience ?? ""} onChange={(e) => set("target_audience", e.target.value)} placeholder="Describe your ideal customer" /></Field>
          <Field label="Product positioning"><Textarea value={f.positioning ?? ""} onChange={(e) => set("positioning", e.target.value)} placeholder="Where you sit in the market and why customers choose you" /></Field>
          <Field label="Brand values" aside="Enter to add"><ChipsInput value={f.values} onChange={(v) => set("values", v)} placeholder="e.g. Sustainability" /></Field>
          <Field label="Marketing guidelines" hint="Do's and don'ts the AI must follow (claims to avoid, words you never use…)."><Textarea rows={4} value={f.marketing_guidelines ?? ""} onChange={(e) => set("marketing_guidelines", e.target.value)} /></Field>
          <Field label="Extra details"><Textarea value={f.extra_details ?? ""} onChange={(e) => set("extra_details", e.target.value)} placeholder="Any additional brand guidelines or context" /></Field>
        </Card>
      </div>

      <div className="flex flex-col gap-4 lg:sticky lg:top-0 lg:self-start">
        <Card className="flex flex-col gap-3 p-4">
          <Button onClick={save} loading={saving} size="lg">{brand ? "Save changes" : "Create brand"}</Button>
          {dirty && <p className="text-center text-xs text-muted">You have unsaved changes</p>}
          <Notice icon={<Info />}>AI models follow brand profiles closely but not perfectly — always review outputs.</Notice>
        </Card>
        <Card className="flex flex-col gap-3 p-4">
          <h3 className="text-[13.5px] font-semibold">Logo</h3>
          {brand?.logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={brand.logo_url} alt="Brand logo" className="checkerboard h-28 w-full rounded-[10px] border border-border object-contain p-2" />
          )}
          <Dropzone compact multiple={false} onFiles={onLogo} label={brand?.logo_url ? "Replace logo" : "Upload logo"} hint="PNG/SVG-exported PNG with transparency works best" disabled={!brand} />
        </Card>
        <Card className="flex flex-col gap-3 p-4">
          <h3 className="text-[13.5px] font-semibold">Guideline documents</h3>
          <p className="text-xs text-muted">PDF, TXT or Markdown. Text is extracted locally and used as context for copy generation.</p>
          {brand?.guidelines.map((g) => (
            <div key={g.id} className="flex items-center gap-2 rounded-[10px] border border-border px-2.5 py-2 text-[13px]">
              <FileText className="size-4 text-muted" /><span className="flex-1 truncate">{g.title}</span>
              <span className="text-[11px] text-muted">{g.chars.toLocaleString()} chars</span>
              <button aria-label={`Remove ${g.title}`} className="text-muted hover:text-danger" onClick={async () => { await del(`/brands/${brand.id}/guidelines/${g.id}`); refresh(); }}><Trash2 className="size-3.5" /></button>
            </div>
          ))}
          <Dropzone compact onFiles={onGuide} accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" label="Upload guidelines" disabled={!brand} />
        </Card>
        {brand && (
          <Button variant="ghost" className="text-danger" onClick={() => setConfirmDelete(true)}><Trash2 />Delete brand</Button>
        )}
      </div>
      {brand && (
        <Confirm open={confirmDelete} onOpenChange={setConfirmDelete} title={`Delete ${brand.name}?`}
          body="Products and creatives stay in your library but will no longer be linked to this brand."
          onConfirm={async () => { await del(`/brands/${brand.id}`); refresh(); toast.success("Brand deleted"); router.push("/brands"); }} />
      )}
    </div>
  );
}
