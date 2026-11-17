"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ClipboardPaste, ExternalLink, FileUp } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/form";
import { post } from "@/lib/api";

export type BrowserImportResult = {
  id: string; name: string; reviews_imported?: number; images_imported?: number;
  import: { kind: "asin" | "walmart" | "url"; id: string; complete: boolean; note: string };
};

const MAX_BYTES = 8_000_000;
const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const key = (win: string, mac: string) => (isMac ? mac : win);

/**
 * Finish an Amazon/Walmart import from the user's own browser: they open the product page as a normal shopper
 * (completing any "are you a robot?" check themselves), then hand Shelfcraft the page by saving it or copying its
 * source. Shelfcraft never tries to get around the marketplace's bot check itself.
 */
export function BrowserPageImport({ productId, pageUrl, brandId, onDone, compact }: {
  productId?: string; pageUrl?: string | null; brandId?: string | null; compact?: boolean;
  onDone?: (r: BrowserImportResult) => void;
}) {
  const qc = useQueryClient();
  const [html, setHtml] = React.useState("");
  const [source, setSource] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const market = pageUrl?.includes("walmart.") ? "Walmart" : "Amazon";

  const take = (text: string, from: string) => {
    if (text.length > MAX_BYTES) return toast.error("That page is larger than 8 MB. Save it as “Webpage, HTML only” instead.");
    setHtml(text);
    setSource(`${from} · ${(text.length / 1_000_000).toFixed(text.length < 100_000 ? 2 : 1)} MB`);
  };

  const run = async () => {
    setBusy(true);
    try {
      const r = await post<BrowserImportResult>("/products/import-html", { html, product_id: productId ?? null, brand_id: brandId || null });
      for (const k of [["products"], ["product", r.id], ["dashboard"]]) qc.invalidateQueries({ queryKey: k });
      toast.success(`“${r.name}” imported from your browser page`);
      setHtml(""); setSource(null);
      onDone?.(r);
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-3 rounded-[12px] border border-border bg-sunken p-4 text-[13px]">
      {!compact && <div className="font-semibold">Finish the import from your browser</div>}
      <ol className="flex list-decimal flex-col gap-2 pl-5">
        <li>
          {pageUrl
            ? <>Open the <a href={pageUrl} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-medium underline">{market} product page<ExternalLink className="size-3" /></a> in your browser.</>
            : <>Open the Amazon or Walmart product page in your browser.</>}
          {" "}If it asks you to confirm you’re not a robot, do that there. You’re a normal visitor.
        </li>
        <li>
          Then hand the page to Shelfcraft, either way works:
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}><FileUp />Upload saved page</Button>
              <span className="text-[11.5px] text-muted">Press <kbd>{key("Ctrl+S", "⌘S")}</kbd> on the product page, save it, then pick the .html file.</span>
              <input ref={fileRef} type="file" accept=".html,.htm,.mhtml,text/html" className="hidden"
                onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) take(await f.text(), f.name); }} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Textarea rows={2} value="" placeholder={`Click here and paste (${key("Ctrl+V", "⌘V")})`} aria-label="Paste the page source"
                onPaste={(e) => { e.preventDefault(); take(e.clipboardData.getData("text"), "Pasted page source"); }}
                onChange={() => undefined} className="min-h-0 resize-none" />
              <span className="text-[11.5px] text-muted">Press <kbd>{key("Ctrl+U", "⌥⌘U")}</kbd> on the product page to view its source, then <kbd>{key("Ctrl+A", "⌘A")}</kbd>, <kbd>{key("Ctrl+C", "⌘C")}</kbd>.</span>
            </div>
          </div>
        </li>
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={run} loading={busy} disabled={!html}><ClipboardPaste />Import from this page</Button>
        <span className="text-[12px] text-muted">{source ?? "Nothing added yet."}</span>
      </div>
      <p className="text-[11.5px] text-muted">
        Shelfcraft reads the title, bullets, description, price, specs, photos and the reviews shown on the page, then runs Deep Strategy on those reviews.
        The page stays on this computer. Only the product photos are downloaded from the marketplace’s image server.
      </p>
    </div>
  );
}
