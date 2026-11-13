"use client";
import {
  ArrowLeft, Clapperboard, FileText, Images, LayoutTemplate, Lightbulb, Megaphone, Mic, Monitor, RectangleHorizontal, RectangleVertical,
  RotateCw, ShoppingBag, Smartphone, Store, Video,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { QuickAddProduct } from "@/components/quick-add-product";
import { ProductSelect } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Badge, Card, OptionCard } from "@/components/ui/misc";
import { cn } from "@/lib/utils";

type Step = "root" | "listings" | "ads" | "aplus" | "videos" | "strategy";

const TITLES: Record<Step, string> = {
  root: "What should we work on?", listings: "Which listing should we work on?", ads: "Which ad format?",
  aplus: "Which A+ content should we work on?", videos: "Which video format?", strategy: "Which product should we analyze?",
};

export default function CreatePage() {
  const [step, setStep] = React.useState<Step>("root");
  const router = useRouter();
  const [aplus, setAplus] = React.useState<string[]>([]);
  const [productId, setProductId] = React.useState("");
  return (
    <div className="mx-auto max-w-3xl py-4">
      {step !== "root" && (
        <div className="mb-4 flex items-center gap-2 text-[13px] text-muted">
          <button onClick={() => setStep("root")} className="inline-flex items-center gap-1.5 hover:text-foreground"><ArrowLeft className="size-4" />Back</button>
          <span>·</span><span className="capitalize">{step}</span>
        </div>
      )}
      <h1 className="mb-1 text-center text-[28px] font-semibold">{TITLES[step]}</h1>
      <p className="mb-8 text-center text-[13.5px] text-muted">Everything runs on free or local AI. Your product photos are never altered without asking.</p>

      {step === "root" && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <OptionCard icon={<FileText />} title="Listings" description="Amazon, Amazon Mobile, Shopify, TikTok Shop, Walmart" onClick={() => setStep("listings")} />
            <OptionCard icon={<Megaphone />} title="Amazon Ads" description="Sponsored Brand & Products, social ads" onClick={() => setStep("ads")} />
            <OptionCard icon={<LayoutTemplate />} title="A+ Content" description="Premium desktop & mobile, Basic" onClick={() => setStep("aplus")} />
            <OptionCard icon={<Clapperboard />} title="Videos" description="Listing, voiceover, 360°, sponsored, reels" onClick={() => setStep("videos")} />
          </div>
          <div className="my-5 flex items-center gap-3 text-xs text-muted"><div className="h-px flex-1 bg-border" />or<div className="h-px flex-1 bg-border" /></div>
          <OptionCard icon={<Lightbulb />} title="Deep Strategy" description="Customer insights, personas and competitor gaps" onClick={() => setStep("strategy")} />
        </>
      )}

      {step === "listings" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[["amazon", "Amazon", "Copy + 7 editable visuals", <ShoppingBag key="a" />], ["amazon_mobile", "Amazon Mobile", "Mobile-optimized copy + visuals", <Smartphone key="m" />],
            ["shopify", "Shopify", "Copy + 7 editable visuals", <Store key="s" />], ["tiktok", "TikTok Shop", "Copy + 7 editable visuals", <Megaphone key="t" />],
            ["walmart", "Walmart", "Copy + 7 editable visuals", <Store key="w" />]].map(([k, t, d, icon]) => (
            <OptionCard key={k as string} icon={icon} title={t as string} description={d as string} href={`/listings/new?marketplace=${k}`} />
          ))}
          <OptionCard icon={<Images />} title="Main images" description="White-background main images" href="/studio?type=white_bg_main" />
        </div>
      )}

      {step === "ads" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {[["sb_image", "Sponsored Brand image", "1200 × 628", <RectangleHorizontal key="1" />], ["sb_video", "Sponsored Brand video", "1920 × 1080 · 10 s", <Video key="2" />],
            ["sp_video", "Sponsored Products video", "1920 × 1080 · 10 s", <Video key="3" />], ["social_feed", "Social feed ad", "1080 × 1350", <RectangleVertical key="4" />],
            ["story_ad", "Story / Reels ad", "1080 × 1920 · 10 s", <RectangleVertical key="5" />]].map(([k, t, d, icon]) => (
            <OptionCard key={k as string} icon={icon} title={t as string} description={d as string} href={`/ads/new?format=${k}`} />
          ))}
        </div>
      )}

      {step === "aplus" && (
        <div className="flex flex-col gap-5">
          {[["premium", "Premium"], ["basic", "Basic"], ["mobile", "Premium Mobile"]].map(([tier, label]) => (
            <div key={tier}>
              <div className="mb-2 text-[13px] font-semibold">{label}</div>
              <div className="grid gap-2 sm:grid-cols-3">
                {[["seamless", "Seamless modules", "One continuous image"], ["separate", "Separate modules", "Standalone modules"], ["single", "Single module", `1 ${label} module`]].map(([mode, t, d]) => {
                  const key = `${tier}:${mode}`;
                  const on = aplus.includes(key);
                  return (
                    <button key={key} onClick={() => setAplus((s) => (on ? s.filter((x) => x !== key) : [key]))}
                      className={cn("rounded-[12px] border p-3 text-left transition", on ? "border-primary ring-3 ring-[var(--ring)]" : "border-border hover:bg-sunken")}>
                      <div className="text-[13.5px] font-semibold">{t}</div><div className="text-xs text-muted">{d}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <div className="flex items-center justify-between rounded-[12px] border border-border bg-surface px-4 py-3">
            <span className="text-[13px] text-muted">{aplus.length ? "1 selected" : "Select a format"}</span>
            <Button disabled={!aplus.length} onClick={() => { const [tier, mode] = aplus[0].split(":"); router.push(`/aplus/new?tier=${tier}&mode=${mode}`); }}>Continue</Button>
          </div>
        </div>
      )}

      {step === "videos" && (
        <div className="flex flex-col gap-4">
          <div className="text-[13px] font-semibold">Amazon</div>
          <div className="grid gap-3 sm:grid-cols-2">
            <OptionCard icon={<Monitor />} title="Listing video" description="16:9 · product slideshow with captions" href="/videos/new?aspect=16:9" />
            <OptionCard icon={<Mic />} title="Voiceover video" description="9:16 · creator-style script + offline AI voice" href="/videos/new?aspect=9:16&mode=voiceover"
              badge={<Badge>no avatar</Badge>} />
            <OptionCard icon={<RotateCw />} title="360° spin" description="Turntable video from your angle photos" href="/videos/spin" />
            <OptionCard icon={<Video />} title="Sponsored Products" description="16:9 · 10 s ad video" href="/ads/new?format=sp_video" />
          </div>
          <div className="text-[13px] font-semibold">Instagram / TikTok</div>
          <div className="grid gap-3 sm:grid-cols-2">
            <OptionCard icon={<Mic />} title="Voiceover reel" description="9:16 · hook, benefits, call to action" href="/videos/new?aspect=9:16&mode=voiceover" />
            <OptionCard icon={<RectangleVertical />} title="Reels ad" description="9:16 · 10 s with text overlays" href="/ads/new?format=story_ad" />
          </div>
        </div>
      )}

      {step === "strategy" && (
        <Card className="flex flex-col gap-3 p-5">
          <div className="flex items-center justify-between text-[13px] font-medium">Product<QuickAddProduct onCreated={setProductId} /></div>
          <ProductSelect value={productId} onChange={setProductId} />
          <p className="text-xs text-muted">You&apos;ll be able to paste customer reviews and competitor notes for deeper insights.</p>
          <Button disabled={!productId} onClick={() => router.push(`/products/${productId}?tab=intelligence`)}>Continue</Button>
        </Card>
      )}

      <p className="mt-10 text-center text-xs text-muted"><Link href="/settings" className="underline">AI providers</Link> · all free or local · nothing is billed</p>
    </div>
  );
}
