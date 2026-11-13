"use client";
import { CircleAlert, Cpu, Cloud, LoaderCircle, Sparkles } from "lucide-react";
import { Tabs as RT } from "radix-ui";
import Link from "next/link";
import * as React from "react";
import { cn, providerLabel } from "@/lib/utils";
import { Button } from "./button";

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-[14px] border border-border bg-surface shadow-[var(--shadow-card)]", className)} {...p} />;
}

export function CardHeader({ title, description, action, className }: { title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-3 px-5 pt-4", className)}>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold">{title}</h3>
        {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}

const badgeTones = {
  neutral: "bg-sunken text-muted",
  primary: "bg-primary-soft text-primary",
  ai: "bg-ai-soft text-ai",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-[color-mix(in_oklch,var(--warning)_70%,black)] dark:text-warning",
  danger: "bg-danger-soft text-danger",
};
export function Badge({ tone = "neutral", className, ...p }: React.HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof badgeTones }) {
  return <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11.5px] font-medium [&_svg]:size-3", badgeTones[tone], className)} {...p} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} aria-hidden />;
}

export function Progress({ value, className, tone = "primary" }: { value: number; className?: string; tone?: "primary" | "ai" }) {
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-sunken", className)} role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cn("h-full rounded-full transition-[width] duration-500", tone === "ai" ? "bg-ai" : "bg-primary")} style={{ width: `${Math.max(3, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={cn("size-4 animate-spin text-muted", className)} />;
}

export function PageHeader({ title, description, actions, eyebrow, className }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mb-6 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted">{eyebrow}</div>}
        <h1 className="text-[26px] font-semibold leading-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13.5px] text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ icon, title, body, action, className }: { icon: React.ReactNode; title: string; body: string; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-[14px] border border-dashed border-border-strong px-6 py-14 text-center", className)}>
      <div className="mb-3 flex size-11 items-center justify-center rounded-[12px] bg-sunken text-muted [&_svg]:size-5">{icon}</div>
      <h3 className="text-[15px] font-semibold">{title}</h3>
      <p className="mt-1 max-w-sm text-[13px] text-muted">{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: { message: string } | null | undefined; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-[12px] border border-danger/30 bg-danger-soft px-4 py-3 text-[13px]">
      <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" />
      <div className="flex-1">
        <div className="font-medium text-danger">Couldn&apos;t load this</div>
        <div className="text-foreground/80">{error?.message ?? "Unknown error"}</div>
      </div>
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Notice({ tone = "neutral", icon, children, className }: { tone?: "neutral" | "ai" | "warning" | "danger" | "success"; icon?: React.ReactNode; children: React.ReactNode; className?: string }) {
  const tones = { neutral: "bg-sunken border-border", ai: "bg-ai-soft border-ai/20", warning: "bg-warning-soft border-warning/30", danger: "bg-danger-soft border-danger/30", success: "bg-success-soft border-success/30" };
  return <div className={cn("flex items-start gap-2.5 rounded-[12px] border px-3.5 py-2.5 text-[13px] [&>svg]:mt-0.5 [&>svg]:size-4 [&>svg]:shrink-0", tones[tone], className)}>{icon}<div className="min-w-0 flex-1">{children}</div></div>;
}

/** Attribution chip shown on every generated result. */
export function ProviderBadge({ provider, model, ai }: { provider?: string | null; model?: string | null; ai?: boolean }) {
  if (!provider) return null;
  const local = ["ollama", "local_diffusion", "rembg", "lama", "opencv", "ffmpeg", "shelfcraft"].includes(provider);
  return (
    <Badge tone={ai ? "ai" : "neutral"} title={model ?? undefined} className="max-w-full">
      {ai ? <Sparkles /> : local ? <Cpu /> : <Cloud />}
      <span className="truncate">{ai ? "" : "Non-AI · "}{providerLabel(provider)}{model ? ` · ${model}` : ""}</span>
    </Badge>
  );
}

export function Tabs({ value, onValueChange, tabs, children, className }: { value: string; onValueChange: (v: string) => void; tabs: { value: string; label: React.ReactNode; count?: number }[]; children?: React.ReactNode; className?: string }) {
  return (
    <RT.Root value={value} onValueChange={onValueChange} className={className}>
      <RT.List className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
        {tabs.map((t) => (
          <RT.Trigger key={t.value} value={t.value}
            className="relative -mb-px whitespace-nowrap border-b-2 border-transparent px-3 pb-2.5 pt-1 text-[13.5px] font-medium text-muted transition-colors hover:text-foreground data-[state=active]:border-primary data-[state=active]:text-foreground">
            {t.label}{t.count !== undefined && <span className="ml-1.5 rounded-full bg-sunken px-1.5 text-[11px] text-muted">{t.count}</span>}
          </RT.Trigger>
        ))}
      </RT.List>
      {children}
    </RT.Root>
  );
}
export const TabPanel = RT.Content;

export function OptionCard({ icon, title, description, onClick, href, selected, disabled, badge, className }: {
  icon: React.ReactNode; title: string; description?: string; onClick?: () => void; href?: string; selected?: boolean; disabled?: boolean; badge?: React.ReactNode; className?: string;
}) {
  const inner = (
    <>
      <div className="flex size-10 shrink-0 items-center justify-center rounded-[11px] bg-primary-soft text-primary [&_svg]:size-5">{icon}</div>
      <div className="min-w-0 flex-1 text-left">
        <div className="flex items-center gap-2 text-[14px] font-semibold">{title}{badge}</div>
        {description && <div className="mt-0.5 text-[12.5px] leading-snug text-muted">{description}</div>}
      </div>
    </>
  );
  const cls = cn("group flex w-full items-center gap-3.5 rounded-[14px] border bg-surface p-3.5 transition-all hover:border-border-strong hover:shadow-[var(--shadow-card)] disabled:pointer-events-none disabled:opacity-50",
    selected ? "border-primary ring-3 ring-[var(--ring)]" : "border-border", className);
  if (href) return <Link href={href} className={cls}>{inner}</Link>;
  return <button type="button" onClick={onClick} disabled={disabled} className={cls} aria-pressed={selected}>{inner}</button>;
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-border bg-sunken px-1.5 py-0.5 font-mono text-[10.5px] text-muted">{children}</kbd>;
}

export function Stat({ label, value, hint, icon }: { label: string; value: React.ReactNode; hint?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="flex items-center justify-between text-[12.5px] text-muted">{label}<span className="[&_svg]:size-4">{icon}</span></div>
      <div className="mt-1 font-display text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}
