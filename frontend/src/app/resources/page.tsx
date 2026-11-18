"use client";
import { BookOpen, ChevronRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { Input } from "@/components/ui/form";
import { Badge, Card, PageHeader } from "@/components/ui/misc";

type Guide = { id: string; title: string; minutes: number; tags: string[]; summary: string; steps: [string, string?][] };

const GUIDES: Guide[] = [
  { id: "first-listing", title: "Your first listing in 5 minutes", minutes: 5, tags: ["Start here", "Listings"],
    summary: "Import a product by ASIN, Walmart ID or URL, generate copy and the full image set.",
    steps: [["Open Create → Listings and pick a marketplace.", "/create"], ["Paste an Amazon ASIN, Walmart item ID or product URL in “Import a product”, then Import."],
      ["Check the imported title, bullets and photos (open the product if anything is missing)."], ["Click Generate listing. Copy is written in the background."],
      ["Open the Image set tab → Generate image set for main, lifestyle and infographic visuals."], ["Use Add more visuals with a prompt to keep going in the same set."]] },
  { id: "strategy", title: "Deep Strategy from your reviews", minutes: 3, tags: ["Strategy"],
    summary: "Turn reviews and competitor notes into personas, objections and creative angles.",
    steps: [["Import by ASIN/Walmart ID — reviews on the page are read and analysed automatically."], ["Or open a product → Research and paste reviews / competitor notes.", "/products"],
      ["Use the personas and objections as prompts in Image studio and Ads studio."]] },
  { id: "edit", title: "Edit any visual: layers and spot edit", minutes: 4, tags: ["Editor"],
    summary: "Every generated image opens as editable layers; spot edit fixes one area.",
    steps: [["On any result, click Edit layers to open the layered editor."], ["Double-click text to rewrite it; drag, resize or recolor any layer."],
      ["For a flat image, use Spot edit to remove objects, replace the background or upscale.", "/edit"], ["Turn any image into layers from the Library (Convert to layers)."]] },
  { id: "figma", title: "Export to Figma, Illustrator or Canva", minutes: 1, tags: ["Export"],
    summary: "Download an editable SVG with real text and vector shapes.",
    steps: [["Open a design in the editor."], ["Export → SVG layers (Figma · Illustrator · Canva)."], ["Drag the .svg into Figma (or File → Import in Illustrator / Canva uploads)."]] },
  { id: "aplus", title: "A+ content, desktop and mobile", minutes: 4, tags: ["A+"],
    summary: "Build Premium or Basic modules, then create the mobile version in one click.",
    steps: [["Create → A+ Content, choose modules and a product.", "/aplus/new"], ["Edit each module in the editor; drag rows to reorder."],
      ["Click Make mobile version — your edited text and images are carried over."], ["Export ZIP for upload in A+ Content Manager."]] },
  { id: "scale", title: "Scale: variants, translations, other products", minutes: 3, tags: ["Scale"],
    summary: "Reuse one finished listing for colors, markets and other products.",
    steps: [["Open Scale and pick Variant, Translate, Different Product or Steal the Look.", "/scale"], ["Choose the source designs and the targets."], ["Track runs under My runs; download ZIPs when finished."]] },
  { id: "factory", title: "Factory: 50 listings at once", minutes: 3, tags: ["Bulk"],
    summary: "Queue creatives for many products × variants with a time estimate first.",
    steps: [["Open Factory, select products and creative types.", "/factory"], ["Preview the count and CPU estimate, then start."], ["Retry failed items and download one ZIP per product."]] },
  { id: "share", title: "Share with your team or client", minutes: 1, tags: ["Share"],
    summary: "A view-only gallery link — no sign-in needed.",
    steps: [["On a listing, A+ or video page click Share → Create share link."], ["Copy the link. Others on your network can open it (start Shelfcraft with the -Lan / --lan option)."], ["Revoke it any time from the same dialog."]] },
  { id: "models", title: "Choose AI models (free and premium)", minutes: 2, tags: ["Settings"],
    summary: "Free local models by default; optional Nano Banana and GPT with your own key.",
    steps: [["Settings → AI providers shows every engine and its state.", "/settings"], ["Free: Ollama (text) and local diffusion (images) run on this PC."],
      ["Premium: turn on “Allow paid providers”, enable Nano Banana or OpenAI with your key."], ["Pick the premium model in a generator's AI selector — it's never used automatically."]] },
  { id: "api", title: "Automate with the API and MCP", minutes: 2, tags: ["API"],
    summary: "Drive Shelfcraft from scripts or AI assistants.",
    steps: [["Settings → API & MCP → create a key.", "/settings?tab=api"], ["Call the /v1 endpoints (docs at /v1/docs on the API port)."], ["Connect backend/mcp_server.py to Claude, Cursor or another MCP client."]] },
];

export default function ResourcesPage() {
  const [q, setQ] = React.useState("");
  const [open, setOpen] = React.useState<string | null>(GUIDES[0].id);
  const list = GUIDES.filter((g) => !q || `${g.title} ${g.summary} ${g.tags.join(" ")}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="Resources" title="Guides" description="Short walkthroughs to get the most out of Shelfcraft." />
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search guides…" className="mb-4" aria-label="Search guides" />
      <div className="flex flex-col gap-3">
        {list.map((g) => (
          <Card key={g.id} className="overflow-hidden">
            <button type="button" onClick={() => setOpen(open === g.id ? null : g.id)} className="flex w-full items-start gap-3 p-4 text-left" aria-expanded={open === g.id}>
              <BookOpen className="mt-0.5 size-4 shrink-0 text-primary" />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 text-[14.5px] font-semibold">{g.title}<Badge>{g.minutes} min</Badge>{g.tags.map((t) => <Badge key={t} tone="primary">{t}</Badge>)}</span>
                <span className="mt-0.5 block text-[13px] text-muted">{g.summary}</span>
              </span>
              <ChevronRight className={`mt-0.5 size-4 shrink-0 text-muted transition-transform ${open === g.id ? "rotate-90" : ""}`} />
            </button>
            {open === g.id && (
              <ol className="flex flex-col gap-2 border-t border-border px-4 py-3 pl-11 text-[13.5px]">
                {g.steps.map(([text, href], i) => (
                  <li key={i} className="list-decimal">{text}{href && <> <Link href={href} className="text-primary underline">Open</Link></>}</li>
                ))}
              </ol>
            )}
          </Card>
        ))}
        {!list.length && <p className="py-8 text-center text-muted">No guides match “{q}”.</p>}
      </div>
    </div>
  );
}
