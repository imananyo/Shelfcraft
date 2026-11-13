"use client";
import {
  ArrowLeft, Clapperboard, Factory, FileText, Images, LayoutTemplate, Lightbulb, Megaphone, PenLine, ScanSearch, ShoppingBag, Sparkles, Store, WandSparkles,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { OptionCard } from "@/components/ui/misc";

type Step = "root" | "listing" | "images";

const MARKETS = [
  { key: "amazon", title: "Amazon", description: "Title, 5 bullets, search terms + 7-image set", icon: <ShoppingBag /> },
  { key: "shopify", title: "Shopify", description: "Product page copy + image set", icon: <Store /> },
  { key: "walmart", title: "Walmart", description: "Short titles, key features + images", icon: <Store /> },
  { key: "tiktok", title: "TikTok Shop", description: "Punchy copy + social-first images", icon: <Megaphone /> },
];

const IMAGE_TYPES = [
  { key: "white_bg_main", title: "White-background main", description: "Your real photo, background removed", icon: <Images /> },
  { key: "lifestyle", title: "Lifestyle scene", description: "AI scene + your untouched product", icon: <Sparkles /> },
  { key: "hero", title: "Premium hero", description: "Studio pedestal, dramatic light", icon: <Sparkles /> },
  { key: "feature", title: "Feature callouts", description: "Infographic with real, editable text", icon: <LayoutTemplate /> },
  { key: "comparison", title: "Comparison chart", description: "You vs. typical alternative", icon: <LayoutTemplate /> },
  { key: "dimensions", title: "Dimensions", description: "Size graphic from your specs", icon: <LayoutTemplate /> },
  { key: "steps", title: "How-to steps", description: "3-step usage graphic", icon: <LayoutTemplate /> },
  { key: "social", title: "Social post", description: "4:5 promo with CTA", icon: <Megaphone /> },
  { key: "ad_sb", title: "Sponsored Brand image", description: "1200×628 ad creative", icon: <Megaphone /> },
];

export default function CreatePage() {
  const [step, setStep] = React.useState<Step>("root");
  return (
    <div className="mx-auto max-w-3xl py-4">
      {step !== "root" && (
        <button onClick={() => setStep("root")} className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-foreground"><ArrowLeft className="size-4" />Back</button>
      )}
      <h1 className="mb-1 text-center text-[28px] font-semibold">
        {step === "root" ? "What should we work on?" : step === "listing" ? "Which marketplace?" : "Which kind of image?"}
      </h1>
      <p className="mb-8 text-center text-[13.5px] text-muted">
        {step === "root" ? "Everything runs on free or local AI. Your product photos are never altered without asking."
          : step === "listing" ? "We'll write the copy, then build an editable image set." : "Pick one — you can generate more types later."}
      </p>
      {step === "root" && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <OptionCard icon={<FileText />} title="Listing" description="Amazon, Shopify, Walmart, TikTok Shop" onClick={() => setStep("listing")} />
            <OptionCard icon={<Images />} title="Images" description="Main, lifestyle, infographics, ads" onClick={() => setStep("images")} />
            <OptionCard icon={<LayoutTemplate />} title="A+ Content" description="Basic & Premium modules, editable" href="/aplus/new" />
            <OptionCard icon={<Clapperboard />} title="Video" description="Listing, reel & ad slideshows (MP4)" href="/videos/new" />
          </div>
          <div className="my-5 flex items-center gap-3 text-xs text-muted"><div className="h-px flex-1 bg-border" />or<div className="h-px flex-1 bg-border" /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <OptionCard icon={<Lightbulb />} title="Product intelligence" description="Personas, positioning, objections" href="/products?intent=research" />
            <OptionCard icon={<ScanSearch />} title="Inspire from a reference" description="Reuse a layout's design principles" href="/inspire" />
            <OptionCard icon={<WandSparkles />} title="Spot edit an image" description="Remove, replace, extend, enhance" href="/edit" />
            <OptionCard icon={<Factory />} title="Bulk factory" description="Many products × many creatives" href="/factory" />
            <OptionCard icon={<PenLine />} title="Design from scratch" description="Open the layered editor" href="/projects?new=1" />
          </div>
        </>
      )}
      {step === "listing" && <div className="grid gap-3 sm:grid-cols-2">{MARKETS.map((m) => <OptionCard key={m.key} icon={m.icon} title={m.title} description={m.description} href={`/listings/new?marketplace=${m.key}`} />)}</div>}
      {step === "images" && <div className="grid gap-3 sm:grid-cols-2">{IMAGE_TYPES.map((t) => <OptionCard key={t.key} icon={t.icon} title={t.title} description={t.description} href={`/studio?type=${t.key}`} />)}</div>}
      <p className="mt-10 text-center text-xs text-muted"><Link href="/settings" className="underline">AI providers</Link> · all free or local · nothing is billed</p>
    </div>
  );
}
