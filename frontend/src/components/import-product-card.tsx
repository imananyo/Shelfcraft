"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Download, FileCode2, Link2, ShoppingBag, Store } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { Card, Notice, Tabs } from "@/components/ui/misc";
import { BrowserPageImport } from "@/components/browser-page-import";
import { post } from "@/lib/api";

type Kind = "asin" | "walmart" | "url";
type ImportResult = { id: string; name: string; import: { kind: Kind; id: string; complete: boolean; note: string; blocked?: boolean; page_url?: string } };

const TABS: { value: Kind; label: React.ReactNode; placeholder: string; hint: string }[] = [
  { value: "asin", label: <span className="inline-flex items-center gap-1.5"><ShoppingBag className="size-3.5" />Amazon ASIN</span>,
    placeholder: "B08N5WRWNW or https://www.amazon.com/dp/B08N5WRWNW", hint: "10-character ASIN, or paste any Amazon product link." },
  { value: "walmart", label: <span className="inline-flex items-center gap-1.5"><Store className="size-3.5" />Walmart item ID</span>,
    placeholder: "5129928603 or https://www.walmart.com/ip/…/5129928603", hint: "Numeric item ID, or paste a walmart.com/ip/… link." },
  { value: "url", label: <span className="inline-flex items-center gap-1.5"><Link2 className="size-3.5" />Product URL</span>,
    placeholder: "https://yourstore.com/products/…", hint: "Any public product page (Shopify, your own site…). Amazon/Walmart links are detected automatically." },
];

/** "Start from an existing product" — import by Amazon ASIN, Walmart item ID or product URL, then hand back the new product id. */
export function ImportProductCard({ country, brandId, onImported }: { country: string; brandId?: string | null; onImported: (id: string, kind: Kind) => void }) {
  const qc = useQueryClient();
  const [kind, setKind] = React.useState<Kind | "page">("asin");
  const [value, setValue] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<ImportResult | null>(null);
  const tab = TABS.find((t) => t.value === kind) ?? TABS[0];
  const finished = (r: ImportResult) => { setResult(r); onImported(r.id, r.import.kind); };

  const run = async () => {
    if (kind === "page") return;
    if (!value.trim()) return toast.error(`Enter ${kind === "url" ? "a product URL" : kind === "asin" ? "an ASIN" : "a Walmart item ID"} first.`);
    setBusy(true);
    try {
      const r = await post<ImportResult>("/products/import-source", { kind, value: value.trim(), country, brand_id: brandId || null });
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      setResult(r);
      setValue("");
      toast.success(`“${r.name}” imported and selected`);
      onImported(r.id, r.import.kind);
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div>
        <div className="text-[14px] font-semibold">Import a product</div>
        <div className="text-[12.5px] text-muted">Start from an existing listing: paste an Amazon ASIN, a Walmart item ID or a product URL.</div>
      </div>
      <Tabs value={kind} onValueChange={(v) => { setKind(v as Kind | "page"); setResult(null); }} className="[&>div]:mb-0"
        tabs={[...TABS.map(({ value, label }) => ({ value, label })),
          { value: "page", label: <span className="inline-flex items-center gap-1.5"><FileCode2 className="size-3.5" />From your browser</span> }]} />
      {kind === "page" ? (
        <BrowserPageImport compact brandId={brandId} onDone={finished} />
      ) : (
        <>
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); run(); }}>
            <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder={tab.placeholder} aria-label={tab.hint} className="flex-1" />
            <Button type="submit" loading={busy}><Download />Import</Button>
          </form>
          <div className="text-[12px] text-muted">{tab.hint}</div>
        </>
      )}
      {result && (
        <Notice tone={result.import.complete ? "success" : "warning"}>
          {result.import.note}{" "}
          <Link href={`/products/${result.id}`} className="underline">Open product</Link>
        </Notice>
      )}
      {result?.import.blocked && (
        <BrowserPageImport productId={result.id} pageUrl={result.import.page_url} brandId={brandId} onDone={finished} />
      )}
    </Card>
  );
}
