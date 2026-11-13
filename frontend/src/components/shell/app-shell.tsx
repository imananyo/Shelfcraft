"use client";
import { useQueryClient } from "@tanstack/react-query";
import {
  Bell, Check, ChevronsUpDown, ListChecks, LoaderCircle, Moon, PanelLeft, Plus, Search, Sun, SunMoon, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";
import { ErrorBoundary } from "@/components/providers";
import { Badge, Kbd, Progress } from "@/components/ui/misc";
import { Menu, MenuItem, MenuLabel, MenuSeparator, Popover, Tip } from "@/components/ui/overlay";
import { post } from "@/lib/api";
import { activateBrand, useActiveBrand, useApi, useSettings } from "@/lib/hooks";
import type { Job } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { LogoMark } from "./logo";
import { ALL_NAV, NAV } from "./nav";

const FULL_BLEED = ["/editor/"]; // routes that manage their own layout

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [searchOpen, setSearchOpen] = React.useState(false);

  React.useEffect(() => {
    try {
      const saved = localStorage.getItem("shelfcraft-sidebar");
      if (saved) setCollapsed(saved === "collapsed");
      else if (window.innerWidth < 1180) setCollapsed(true);
    } catch { /* storage unavailable */ }
  }, []);
  React.useEffect(() => setMobileOpen(false), [pathname]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggle = () => {
    if (window.innerWidth < 1024) return setMobileOpen((o) => !o);
    setCollapsed((c) => {
      try { localStorage.setItem("shelfcraft-sidebar", c ? "expanded" : "collapsed"); } catch { /* ignore */ }
      return !c;
    });
  };

  const fullBleed = FULL_BLEED.some((p) => pathname.startsWith(p));
  return (
    <div className="flex h-full">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setMobileOpen(false)} />}
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} pathname={pathname} onNavigate={() => setMobileOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onToggle={toggle} onSearch={() => setSearchOpen(true)} pathname={pathname} />
        <main className={cn("min-h-0 flex-1", fullBleed ? "overflow-hidden" : "scrollbar-thin overflow-y-auto")}>
          <ErrorBoundary label="This page">
            {fullBleed ? children : <div className="mx-auto w-full max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>}
          </ErrorBoundary>
        </main>
      </div>
      {searchOpen && <SearchPalette onClose={() => setSearchOpen(false)} />}
    </div>
  );
}

function Sidebar({ collapsed, mobileOpen, pathname, onNavigate }: { collapsed: boolean; mobileOpen: boolean; pathname: string; onNavigate: () => void }) {
  const isActive = (href: string, match?: string[]) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`) || (match ?? []).some((m) => pathname.startsWith(m));
  return (
    <aside
      className={cn(
        "z-40 flex h-full shrink-0 flex-col border-r border-border bg-background transition-[width] duration-200",
        "fixed inset-y-0 left-0 lg:static",
        mobileOpen ? "w-[248px] translate-x-0 shadow-[var(--shadow-pop)]" : "-translate-x-full lg:translate-x-0",
        collapsed ? "lg:w-[64px]" : "lg:w-[248px]",
      )}
    >
      <div className={cn("flex h-[52px] items-center gap-2 px-3", collapsed && "lg:justify-center lg:px-0")}>
        <Link href="/" className="flex items-center gap-2" onClick={onNavigate}>
          <LogoMark />
          <span className={cn("font-display text-[17px] font-semibold tracking-tight", collapsed && "lg:hidden")}>Shelfcraft</span>
        </Link>
      </div>
      <BrandSwitcher collapsed={collapsed} />
      <nav className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-4" aria-label="Main">
        {NAV.map((g) => (
          <div key={g.label || "root"} className="mt-3 first:mt-1">
            {g.label && <div className={cn("px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted", collapsed && "lg:sr-only")}>{g.label}</div>}
            {g.items.map((it) => {
              const active = isActive(it.href, it.match);
              const link = (
                <Link key={it.href} href={it.href} onClick={onNavigate} aria-current={active ? "page" : undefined}
                  className={cn("flex h-8 items-center gap-2.5 rounded-[9px] px-2.5 text-[13.5px] transition-colors",
                    active ? "bg-surface font-medium text-foreground shadow-[var(--shadow-card)] ring-1 ring-border" : "text-foreground/75 hover:bg-sunken hover:text-foreground",
                    collapsed && "lg:justify-center lg:px-0")}>
                  <it.icon className={cn("size-[17px] shrink-0", active ? "text-primary" : "text-muted")} />
                  <span className={cn("truncate", collapsed && "lg:hidden")}>{it.label}</span>
                </Link>
              );
              return collapsed ? <Tip key={it.href} content={it.label} side="right">{link}</Tip> : link;
            })}
          </div>
        ))}
      </nav>
      <ProfileCard collapsed={collapsed} />
    </aside>
  );
}

function BrandSwitcher({ collapsed }: { collapsed: boolean }) {
  const { brand, brands } = useActiveBrand();
  const qc = useQueryClient();
  const router = useRouter();
  const initial = (brand?.name ?? "?").slice(0, 1).toUpperCase();
  const swatch = brand?.colors?.[0] ?? "var(--border-strong)";
  return (
    <div className="px-2">
      <Menu align="start" trigger={
        <button className={cn("flex w-full items-center gap-2.5 rounded-[10px] border border-border bg-surface px-2 py-1.5 text-left hover:border-border-strong", collapsed && "lg:justify-center lg:border-0 lg:bg-transparent lg:px-0")} aria-label="Switch brand">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-[8px] text-[12px] font-semibold text-white" style={{ background: swatch }}>{initial}</span>
          <span className={cn("min-w-0 flex-1", collapsed && "lg:hidden")}>
            <span className="block truncate text-[13px] font-medium">{brand?.name ?? "No brand yet"}</span>
            <span className="block text-[11px] text-muted">Active brand</span>
          </span>
          <ChevronsUpDown className={cn("size-3.5 text-muted", collapsed && "lg:hidden")} />
        </button>
      }>
        <MenuLabel>Brands</MenuLabel>
        {brands.map((b) => (
          <MenuItem key={b.id} onSelect={async () => { await activateBrand(b.id); qc.invalidateQueries({ queryKey: ["settings"] }); }}
            icon={<span className="size-3 rounded-full" style={{ background: b.colors?.[0] ?? "var(--border-strong)" }} />}>
            <span className="flex-1 truncate">{b.name}</span>{brand?.id === b.id && <Check className="!text-primary" />}
          </MenuItem>
        ))}
        {brands.length > 0 && <MenuSeparator />}
        <MenuItem icon={<Plus />} onSelect={() => router.push("/brands/new")}>New brand</MenuItem>
        <MenuItem onSelect={() => router.push("/brands")}>Manage brands</MenuItem>
      </Menu>
    </div>
  );
}

function ProfileCard({ collapsed }: { collapsed: boolean }) {
  const s = useSettings();
  const name = s.data?.display_name ?? "You";
  return (
    <div className="border-t border-border p-2">
      <Link href="/settings" className={cn("flex items-center gap-2.5 rounded-[10px] px-2 py-1.5 hover:bg-sunken", collapsed && "lg:justify-center lg:px-0")}>
        <span className="flex size-7 items-center justify-center rounded-full bg-foreground text-[11px] font-semibold text-background">{name.slice(0, 2).toUpperCase()}</span>
        <span className={cn("min-w-0 flex-1", collapsed && "lg:hidden")}>
          <span className="block truncate text-[13px] font-medium">{name}</span>
          <span className="block text-[11px] text-muted">Local workspace · free</span>
        </span>
      </Link>
    </div>
  );
}

function Topbar({ onToggle, onSearch, pathname }: { onToggle: () => void; onSearch: () => void; pathname: string }) {
  const matches = (href: string, extra?: string[]) => (href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`))
    || (extra ?? []).some((m) => pathname.startsWith(m));
  const current = ALL_NAV.filter((n) => matches(n.href, n.match)).sort((a, b) => b.href.length - a.href.length)[0];
  return (
    <header className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur sm:px-4">
      <Tip content="Toggle sidebar"><button onClick={onToggle} className="flex size-8 items-center justify-center rounded-[8px] text-muted hover:bg-sunken hover:text-foreground" aria-label="Toggle sidebar"><PanelLeft className="size-[18px]" /></button></Tip>
      <div className="hidden text-[13.5px] font-medium sm:block">{current?.label ?? ""}</div>
      <button onClick={onSearch} className="ml-auto flex h-8 w-full max-w-72 items-center gap-2 rounded-[9px] border border-border bg-surface px-2.5 text-[13px] text-muted hover:border-border-strong sm:ml-4" aria-label="Search">
        <Search className="size-3.5" /><span className="flex-1 text-left">Search…</span><Kbd>Ctrl K</Kbd>
      </button>
      <div className="ml-auto flex items-center gap-1">
        <JobTray />
        <Notifications />
        <ThemeToggle />
      </div>
    </header>
  );
}

function JobTray() {
  const q = useApi<{ items: Job[]; counts: Record<string, number> }>(["jobs", "tray"], "/jobs?limit=8", { refetchInterval: 2500 });
  const active = (q.data?.counts.running ?? 0) + (q.data?.counts.queued ?? 0);
  return (
    <Popover trigger={
      <button className="relative flex h-8 items-center gap-1.5 rounded-[8px] px-2 text-muted hover:bg-sunken hover:text-foreground" aria-label="Background jobs">
        {active ? <LoaderCircle className="size-[17px] animate-spin text-ai" /> : <ListChecks className="size-[17px]" />}
        {active > 0 && <span className="text-[12px] font-medium text-ai">{active}</span>}
      </button>
    }>
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <span className="text-[13px] font-semibold">Background jobs</span>
        <Link href="/jobs" className="text-xs font-medium text-primary hover:underline">View all</Link>
      </div>
      <div className="max-h-96 overflow-y-auto p-2">
        {!q.data?.items.length && <div className="px-2 py-6 text-center text-[13px] text-muted">No jobs yet. Generations run here in the background.</div>}
        {q.data?.items.map((j) => (
          <div key={j.id} className="rounded-[10px] px-2 py-2 hover:bg-sunken">
            <div className="flex items-center justify-between gap-2 text-[13px]">
              <span className="truncate font-medium">{j.label}</span>
              <JobStatusBadge status={j.status} />
            </div>
            {j.status === "running" && <Progress value={j.progress} tone="ai" className="mt-1.5" />}
            <div className="mt-1 truncate text-xs text-muted">{j.status === "failed" ? j.error : j.message} · {timeAgo(j.created_at)}</div>
          </div>
        ))}
      </div>
    </Popover>
  );
}

export function JobStatusBadge({ status }: { status: Job["status"] }) {
  const map = { queued: ["neutral", "Queued"], running: ["ai", "Running"], succeeded: ["success", "Done"], failed: ["danger", "Failed"], cancelled: ["neutral", "Cancelled"] } as const;
  const [tone, label] = map[status];
  return <Badge tone={tone}>{label}</Badge>;
}

function Notifications() {
  const qc = useQueryClient();
  const q = useApi<{ unread: number; items: { id: string; level: string; title: string; body?: string; link?: string; read: boolean; created_at: string }[] }>(
    ["notifications"], "/notifications", { refetchInterval: 6000 });
  const unread = q.data?.unread ?? 0;
  return (
    <Popover trigger={
      <button className="relative flex size-8 items-center justify-center rounded-[8px] text-muted hover:bg-sunken hover:text-foreground" aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}>
        <Bell className="size-[17px]" />
        {unread > 0 && <span className="absolute right-1 top-1 size-2 rounded-full bg-danger ring-2 ring-background" />}
      </button>
    }>
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <span className="text-[13px] font-semibold">Notifications</span>
        {unread > 0 && <button className="text-xs font-medium text-primary hover:underline" onClick={async () => { await post("/notifications/read-all"); qc.invalidateQueries({ queryKey: ["notifications"] }); }}>Mark all read</button>}
      </div>
      <div className="max-h-96 overflow-y-auto p-2">
        {!q.data?.items.length && <div className="px-2 py-6 text-center text-[13px] text-muted">You&apos;re all caught up.</div>}
        {q.data?.items.map((n) => {
          const body = (
            <div className={cn("rounded-[10px] px-2.5 py-2 hover:bg-sunken", !n.read && "bg-primary-soft/40")}>
              <div className="flex items-center gap-2 text-[13px] font-medium">
                <span className={cn("size-1.5 rounded-full", n.level === "error" ? "bg-danger" : n.level === "warning" ? "bg-warning" : "bg-success")} />
                <span className="truncate">{n.title}</span>
              </div>
              {n.body && <div className="mt-0.5 line-clamp-2 text-xs text-muted">{n.body}</div>}
              <div className="mt-0.5 text-[11px] text-muted">{timeAgo(n.created_at)}</div>
            </div>
          );
          return n.link ? <Link key={n.id} href={n.link}>{body}</Link> : <div key={n.id}>{body}</div>;
        })}
      </div>
    </Popover>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = React.useState<"light" | "dark" | "system">("system");
  React.useEffect(() => {
    try { setTheme((localStorage.getItem("shelfcraft-theme") as typeof theme) ?? "system"); } catch { /* ignore */ }
  }, []);
  const apply = (t: typeof theme) => {
    setTheme(t);
    try { localStorage.setItem("shelfcraft-theme", t); } catch { /* ignore */ }
    const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
  };
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : SunMoon;
  return (
    <Menu trigger={<button className="flex size-8 items-center justify-center rounded-[8px] text-muted hover:bg-sunken hover:text-foreground" aria-label="Theme"><Icon className="size-[17px]" /></button>}>
      {(["light", "dark", "system"] as const).map((t) => (
        <MenuItem key={t} onSelect={() => apply(t)} icon={t === "light" ? <Sun /> : t === "dark" ? <Moon /> : <SunMoon />}>
          <span className="flex-1 capitalize">{t}</span>{theme === t && <Check className="!text-primary" />}
        </MenuItem>
      ))}
    </Menu>
  );
}

function SearchPalette({ onClose }: { onClose: () => void }) {
  const [q, setQ] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const [idx, setIdx] = React.useState(0);
  const router = useRouter();
  React.useEffect(() => { const t = setTimeout(() => setDebounced(q), 180); return () => clearTimeout(t); }, [q]);
  const res = useApi<{ results: { type: string; id: string; title: string; subtitle?: string; href: string; thumb_url?: string }[] }>(
    ["search", debounced], debounced.length >= 2 ? `/search?q=${encodeURIComponent(debounced)}` : null);
  const pages = ALL_NAV.filter((n) => !q || n.label.toLowerCase().includes(q.toLowerCase())).map((n) => ({ type: "page", id: n.href, title: n.label, href: n.href }));
  const items: { type: string; id: string; title: string; href: string; subtitle?: string }[] = [...(res.data?.results ?? []), ...pages];
  const go = (href: string) => { onClose(); router.push(href); };
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 px-4 pt-[12vh]" onClick={onClose}>
      <div className="w-full max-w-xl overflow-hidden rounded-[16px] border border-border bg-surface shadow-[var(--shadow-pop)]" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-border px-4">
          <Search className="size-4 text-muted" />
          <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setIdx(0); }} placeholder="Search products, brands, designs, assets, pages…"
            className="h-12 flex-1 bg-transparent text-[14px] outline-none"
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(items.length - 1, i + 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
              if (e.key === "Enter" && items[idx]) go(items[idx].href);
            }} />
          <button onClick={onClose} aria-label="Close search" className="text-muted hover:text-foreground"><X className="size-4" /></button>
        </div>
        <div className="max-h-[50vh] overflow-y-auto p-2">
          {items.length === 0 && <div className="px-3 py-8 text-center text-[13px] text-muted">No matches.</div>}
          {items.map((r, i) => (
            <button key={`${r.type}-${r.id}`} onMouseEnter={() => setIdx(i)} onClick={() => go(r.href)}
              className={cn("flex w-full items-center gap-3 rounded-[10px] px-3 py-2 text-left text-[13.5px]", i === idx && "bg-sunken")}>
              <Badge tone={r.type === "page" ? "neutral" : "primary"} className="w-16 justify-center capitalize">{r.type}</Badge>
              <span className="flex-1 truncate">{r.title}</span>
              {r.subtitle && <span className="truncate text-xs text-muted">{r.subtitle}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
