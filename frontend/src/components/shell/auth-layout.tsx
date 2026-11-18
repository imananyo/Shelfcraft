"use client";
import { Eye, EyeOff, Sparkles, Store, Workflow } from "lucide-react";
import { Crimson_Pro, Poppins } from "next/font/google";
import * as React from "react";
import { cn } from "@/lib/utils";
import { LogoMark } from "./logo";

// Retail-house look: monochrome ink on soft grey, Poppins text, serif display headlines, a single honey accent
// and "leaf" corners (three rounded, one square). Original artwork only — no third-party logos or images.
const poppins = Poppins({ subsets: ["latin"], weight: ["300", "400", "500", "600"], variable: "--font-auth-sans" });
const crimson = Crimson_Pro({ subsets: ["latin"], weight: ["400", "500", "600"], style: ["normal", "italic"], variable: "--font-auth-serif" });

const HONEY = "#ffc803";

/** The Shelfcraft mark recoloured to the monochrome palette (ink or paper square, honey spark). */
function Mark({ size, inverse }: { size: number; inverse?: boolean }) {
  const vars = inverse ? { "--primary": "#ffffff", "--primary-foreground": "#0a0a0a" } : { "--primary": "#0a0a0a", "--primary-foreground": "#ffffff" };
  return <span className="flex" style={{ ...vars, "--logo-spark": HONEY } as React.CSSProperties}><LogoMark size={size} /></span>;
}

/** Decorative honeycomb drawn from scratch (pure SVG pattern). */
function Honeycomb({ className }: { className?: string }) {
  return (
    <svg className={className} aria-hidden>
      <defs>
        <pattern id="auth-hex" width="56" height="97" patternUnits="userSpaceOnUse" patternTransform="scale(.9)">
          <path d="M28 0l28 16v32L28 64 0 48V16zM28 64l28 16v33M28 64L0 80v33" fill="none" stroke="currentColor" strokeWidth="1" />
        </pattern>
        <radialGradient id="auth-fade" cx="85%" cy="15%" r="75%">
          <stop offset="0" stopColor="#fff" stopOpacity="1" /><stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
        <mask id="auth-mask"><rect width="100%" height="100%" fill="url(#auth-fade)" /></mask>
      </defs>
      <rect width="100%" height="100%" fill="url(#auth-hex)" mask="url(#auth-mask)" />
    </svg>
  );
}

const POINTS = [
  { icon: Store, title: "Every marketplace", body: "Listing copy, images and A+ for Amazon, Walmart, Shopify and more." },
  { icon: Workflow, title: "Built for portfolios", body: "Playbooks run the same recipe across hundreds of products." },
  { icon: Sparkles, title: "Data-led creative", body: "Reviews and competitor benchmarks shape every listing." },
];

export function AuthLayout({ title, subtitle, children, footer }: {
  title: React.ReactNode; subtitle?: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode;
}) {
  return (
    <div className={cn(poppins.variable, crimson.variable, "fixed inset-0 z-50 grid overflow-y-auto bg-[#f2f2f2] text-[#0a0a0a] lg:grid-cols-[1.05fr_1fr] dark:bg-[#0f0f0f] dark:text-[#f2f2f2]")}
      style={{ fontFamily: "var(--font-auth-sans), ui-sans-serif, system-ui, sans-serif" }}>
      {/* Brand panel */}
      <aside className="relative hidden overflow-hidden bg-[#0a0a0a] text-white lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
        <Honeycomb className="pointer-events-none absolute inset-0 size-full text-white/[.07]" />
        <div className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full blur-3xl" style={{ background: HONEY, opacity: 0.12 }} />
        <div className="relative flex items-center gap-2.5">
          <Mark size={34} inverse />
          <span className="text-[19px] font-semibold tracking-tight">Shelfcraft</span>
        </div>
        <div className="relative max-w-[520px]">
          <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 px-3 py-1 text-[12px] font-medium uppercase tracking-[.14em] text-white/70">
            <span className="size-1.5 rounded-full" style={{ background: HONEY }} />Brand studio
          </p>
          <h2 className="text-[46px] font-medium leading-[1.05] tracking-[-.01em] xl:text-[54px]" style={{ fontFamily: "var(--font-auth-serif), Georgia, serif" }}>
            Grow every brand on the shelf, <em className="italic" style={{ color: HONEY }}>faster</em>.
          </h2>
          <p className="mt-5 max-w-[440px] text-[15px] font-light leading-relaxed text-white/65">
            One workspace for the creative behind a house of brands — from the first listing to the hundredth product.
          </p>
          <ul className="mt-10 grid gap-5">
            {POINTS.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex gap-4">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-[14px_14px_0_14px] bg-white/[.08] ring-1 ring-white/10"><Icon className="size-[18px]" style={{ color: HONEY }} /></span>
                <span><span className="block text-[14px] font-medium">{title}</span><span className="block text-[13px] font-light text-white/55">{body}</span></span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-[12px] font-light text-white/40">Runs on your own computer · free and local AI</p>
      </aside>

      {/* Form panel */}
      <main className="relative flex min-h-full flex-col items-center justify-center bg-gradient-to-b from-[#f2f2f2] to-white px-4 py-10 sm:px-8 dark:from-[#141414] dark:to-[#0f0f0f]">
        <div className="mb-8 flex items-center gap-2.5 lg:hidden"><span className="dark:hidden"><Mark size={32} /></span><span className="hidden dark:block"><Mark size={32} inverse /></span><span className="text-[18px] font-semibold tracking-tight">Shelfcraft</span></div>
        <div className="w-full max-w-[420px] rounded-[20px_20px_0_20px] bg-white p-7 shadow-[0_1px_2px_rgba(0,0,0,.05),0_12px_40px_rgba(73,73,73,.10)] ring-1 ring-black/[.04] sm:p-9 dark:bg-[#181818] dark:ring-white/10">
          <h1 className="text-[34px] font-medium leading-tight tracking-[-.01em]" style={{ fontFamily: "var(--font-auth-serif), Georgia, serif" }}>{title}</h1>
          {subtitle && <p className="mt-1.5 text-[14px] font-light text-[#4a4a4a] dark:text-[#b5b5b5]">{subtitle}</p>}
          <div className="mt-7">{children}</div>
        </div>
        {footer && <div className="mt-6 max-w-[420px] text-center text-[12.5px] font-light text-[#777] dark:text-[#999]">{footer}</div>}
      </main>
    </div>
  );
}

export function AuthField({ label, hint, error, children, aside }: { label: string; hint?: React.ReactNode; error?: React.ReactNode; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="flex items-baseline justify-between text-[13px] font-medium text-[#0a0a0a] dark:text-[#f2f2f2]">{label}{aside}</span>
      {children}
      {error ? <span className="text-[12px] text-[#c0392b] dark:text-[#ff8a7a]">{error}</span> : hint ? <span className="text-[12px] font-light text-[#999]">{hint}</span> : null}
    </label>
  );
}

const inputCls = "h-12 w-full rounded-[12px] border border-[#d9d9d9] bg-[#f9f9f9] px-4 text-[14.5px] text-[#0a0a0a] outline-none transition placeholder:text-[#999] "
  + "focus:border-[#0a0a0a] focus:bg-white focus:ring-4 focus:ring-black/[.06] aria-[invalid=true]:border-[#c0392b] "
  + "dark:border-[#333] dark:bg-[#111] dark:text-white dark:focus:border-white dark:focus:bg-[#151515] dark:focus:ring-white/10";

export const AuthInput = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => <input ref={ref} className={cn(inputCls, className)} {...p} />);
AuthInput.displayName = "AuthInput";

export function PasswordInput({ value, onChange, autoComplete, invalid, onCaps }: {
  value: string; onChange: (v: string) => void; autoComplete: string; invalid?: boolean; onCaps?: (on: boolean) => void;
}) {
  const [show, setShow] = React.useState(false);
  const caps = (e: React.KeyboardEvent<HTMLInputElement>) => onCaps?.(e.getModifierState?.("CapsLock") ?? false);
  return (
    <div className="relative">
      <AuthInput type={show ? "text" : "password"} autoComplete={autoComplete} value={value} required aria-invalid={invalid || undefined}
        onChange={(e) => onChange(e.target.value)} onKeyUp={caps} onKeyDown={caps} onBlur={() => onCaps?.(false)} className="pr-12" />
      <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
        className="absolute right-1.5 top-1/2 flex size-9 -translate-y-1/2 items-center justify-center rounded-[10px] text-[#777] hover:bg-black/5 hover:text-[#0a0a0a] dark:hover:bg-white/10 dark:hover:text-white">
        {show ? <EyeOff className="size-[18px]" /> : <Eye className="size-[18px]" />}
      </button>
    </div>
  );
}

export function AuthButton({ loading, children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) {
  return (
    <button {...p} disabled={p.disabled || loading}
      className="group relative flex h-12 w-full items-center justify-center gap-2 rounded-[30px_30px_0_30px] bg-[#0a0a0a] text-[15px] font-medium text-white transition hover:bg-[#262626] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#ffc803]/60 disabled:opacity-60 dark:bg-white dark:text-[#0a0a0a] dark:hover:bg-[#e9e9e9]">
      {loading && <span className="size-4 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden />}
      {children}
      {!loading && <span aria-hidden className="transition group-hover:translate-x-0.5" style={{ color: HONEY }}>→</span>}
    </button>
  );
}

export function AuthAlert({ children }: { children: React.ReactNode }) {
  return <div role="alert" className="mb-4 rounded-[12px_12px_0_12px] border border-[#c0392b]/25 bg-[#c0392b]/[.06] px-3.5 py-2.5 text-[13px] text-[#a93226] dark:text-[#ff8a7a]">{children}</div>;
}
