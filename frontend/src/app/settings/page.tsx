"use client";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, CircleAlert, CircleCheck, Cloud, Cpu, Database, ExternalLink, HardDrive, KeyRound, ShieldAlert } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Badge, Card, Notice, PageHeader, Skeleton, TabPanel, Tabs } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { download, get, patch, post } from "@/lib/api";
import { useApi, useProviders, useScriptCommand, useSettings } from "@/lib/hooks";
import type { ProviderStatus } from "@/lib/types";
import { formatBytes, timeAgo } from "@/lib/utils";
import { ApiTab, IntegrationsTab, TeamTab } from "./settings-extra";

const STATE: Record<ProviderStatus["state"], { tone: "success" | "neutral" | "warning" | "danger"; label: string }> = {
  available: { tone: "success", label: "Available" }, disabled: { tone: "neutral", label: "Disabled" }, not_configured: { tone: "warning", label: "Not configured" },
  rate_limited: { tone: "warning", label: "Rate-limited" }, unavailable: { tone: "danger", label: "Unavailable" }, ineligible: { tone: "danger", label: "Not free — blocked" }, paid_locked: { tone: "warning", label: "Paid — locked" },
};

function SettingsInner() {
  const sp = useSearchParams();
  const [tab, setTab] = React.useState(sp.get("tab") ?? "providers");
  return (
    <>
      <PageHeader title="Settings" description="Everything runs locally. Hosted AI providers are optional, free-tier only, and never billed." />
      <Tabs value={tab} onValueChange={setTab} tabs={[{ value: "providers", label: "AI providers" }, { value: "defaults", label: "Generation defaults" }, { value: "usage", label: "Usage" }, { value: "notifications", label: "Notifications" }, { value: "team", label: "Team" }, { value: "api", label: "API & MCP" }, { value: "integrations", label: "Integrations" }, { value: "data", label: "Storage & data" }, { value: "prefs", label: "Preferences" }]}>
        <TabPanel value="providers"><Providers /></TabPanel>
        <TabPanel value="defaults"><Defaults /></TabPanel>
        <TabPanel value="notifications"><NotificationPrefs /></TabPanel>
        <TabPanel value="usage"><Usage /></TabPanel>
        <TabPanel value="team"><TeamTab /></TabPanel>
        <TabPanel value="api"><ApiTab /></TabPanel>
        <TabPanel value="integrations"><IntegrationsTab /></TabPanel>
        <TabPanel value="data"><Data /></TabPanel>
        <TabPanel value="prefs"><Prefs /></TabPanel>
      </Tabs>
    </>
  );
}

function Providers() {
  const q = useProviders();
  const s = useSettings();
  const qc = useQueryClient();
  const [privacyFor, setPrivacyFor] = React.useState<ProviderStatus | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["providers"] }); qc.invalidateQueries({ queryKey: ["capabilities"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); };
  const enable = async (p: ProviderStatus, on: boolean) => {
    if (on && !p.local && !s.data?.privacy_ack_hosted) return setPrivacyFor(p);
    try { await patch(`/providers/${p.name}`, { enabled: on }); refresh(); toast.success(`${p.label} ${on ? "enabled" : "disabled"}`); } catch (e) { toast.error((e as Error).message); }
  };
  if (q.isLoading) return <Skeleton className="h-96" />;
  const local = q.data?.filter((p) => p.local) ?? [], hosted = q.data?.filter((p) => !p.local && !p.paid) ?? [], paid = q.data?.filter((p) => p.paid) ?? [];
  const gd = (s.data?.generation_defaults ?? {}) as Record<string, unknown>;
  const allowPaid = !!gd.allow_paid_providers;
  const setAllowPaid = async (on: boolean) => {
    try { await patch("/settings", { generation_defaults: { ...gd, allow_paid_providers: on } }); qc.invalidateQueries({ queryKey: ["settings"] }); refresh(); toast.success(on ? "Paid providers unlocked" : "Paid providers locked"); } catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="flex flex-col gap-6">
      <Notice icon={<ShieldAlert />}>
        <b>Free-only policy.</b> Shelfcraft only calls local models or providers whose recurring free tier was verified (date shown on each card). It never buys credits, never upgrades plans, and paid models are rejected before any request is sent. If every provider is down, the rest of the app keeps working.
      </Notice>
      <section><h2 className="mb-3 flex items-center gap-2 text-[15px] font-semibold"><Cpu className="size-4" />Local (runs on this computer)</h2>
        <div className="grid gap-4 lg:grid-cols-2">{local.map((p) => <ProviderCard key={p.name} p={p} onToggle={(on) => enable(p, on)} onChange={refresh} />)}</div></section>
      <section><h2 className="mb-3 flex items-center gap-2 text-[15px] font-semibold"><Cloud className="size-4" />Hosted free tiers (optional)</h2>
        <div className="grid gap-4 lg:grid-cols-2">{hosted.map((p) => <ProviderCard key={p.name} p={p} onToggle={(on) => enable(p, on)} onChange={refresh} />)}</div></section>
      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold"><KeyRound className="size-4" />Premium models — paid, your own key (optional)</h2>
          <Switch checked={allowPaid} onChange={setAllowPaid} label="Allow paid providers" />
        </div>
        <Notice tone="warning" className="mb-3 text-[12.5px]">The same model families Pixii advertises (Google <b>Nano Banana</b> image models and OpenAI <b>GPT</b> / <b>GPT Image</b>). Each call is <b>billed to your account</b>. They are never used automatically: they run only when this switch is on, the provider is enabled with your key, and you pick it in a generator&apos;s AI selector. Your free providers stay the default.</Notice>
        <div className="grid gap-4 lg:grid-cols-2">{paid.map((p) => <ProviderCard key={p.name} p={p} onToggle={(on) => enable(p, on)} onChange={refresh} />)}</div>
      </section>
      <Dialog open={!!privacyFor} onOpenChange={(o) => !o && setPrivacyFor(null)} title="Before you enable a hosted provider"
        description="Free tiers often allow the provider to log or use prompts to improve their models."
        footer={<><Button variant="ghost" onClick={() => setPrivacyFor(null)}>Cancel</Button><Button onClick={async () => {
          await patch("/settings", { privacy_ack_hosted: true }); qc.invalidateQueries({ queryKey: ["settings"] });
          await patch(`/providers/${privacyFor!.name}`, { enabled: true }); setPrivacyFor(null); refresh(); toast.success("Enabled");
        }}>I understand — enable</Button></>}>
        <div className="flex flex-col gap-2 text-[13px]">
          <p>{privacyFor?.privacy_note}</p>
          <p className="text-muted">Product details, brand profiles and (for vision features) images you choose to analyze may be sent to {privacyFor?.label}. Don&apos;t include confidential information. Local providers (Ollama, local diffusion) never send data anywhere.</p>
        </div>
      </Dialog>
    </div>
  );
}

function ProviderCard({ p, onToggle, onChange }: { p: ProviderStatus; onToggle: (on: boolean) => void; onChange: () => void }) {
  const cmd = useScriptCommand();
  const [key, setKey] = React.useState("");
  const [acct, setAcct] = React.useState(p.extra.account_id ?? "");
  const [model, setModel] = React.useState(p.text_model ?? "");
  const [imgModel, setImgModel] = React.useState(p.image_model ?? "");
  const [models, setModels] = React.useState<string[]>([]);
  const [testing, setTesting] = React.useState(false);
  const [test, setTest] = React.useState<{ ok: boolean; detail: string } | null>(null);
  const st = STATE[p.state];
  const saveCfg = async (body: Record<string, unknown>, msg = "Saved") => { try { await patch(`/providers/${p.name}`, body); toast.success(msg); onChange(); } catch (e) { toast.error((e as Error).message); } };
  const runTest = async () => {
    setTesting(true);
    try { const r = await post<{ ok: boolean; detail: string; models: string[] }>(`/providers/${p.name}/test`); setTest(r); setModels(r.models); } finally { setTesting(false); }
  };
  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><h3 className="text-[14.5px] font-semibold">{p.label}</h3><Badge tone={st.tone}>{st.label}</Badge>{p.kinds.map((k) => <Badge key={k}>{k}</Badge>)}{p.vision && <Badge>vision</Badge>}</div>
          <div className="mt-1 text-xs text-muted">{p.paid ? "Pricing page" : "Free terms checked"} {p.paid ? "" : p.verified_on} · <a href={p.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline">source<ExternalLink className="size-3" /></a></div>
        </div>
        <Switch checked={p.enabled} disabled={p.state === "ineligible"} onChange={onToggle} label={`Enable ${p.label}`} />
      </div>
      <p className="text-[12.5px] leading-relaxed text-muted">{p.limits_note}</p>
      {p.license_note && <p className="text-[12px] text-muted"><b className="text-foreground">License:</b> {p.license_note}</p>}
      {p.requires_key && p.state !== "ineligible" && (
        <div className="flex flex-col gap-2 rounded-[10px] bg-sunken p-3">
          {p.name === "cloudflare" && <Field label="Account ID"><div className="flex gap-2"><Input value={acct} onChange={(e) => setAcct(e.target.value)} placeholder="32-character account ID" /><Button variant="outline" onClick={() => saveCfg({ account_id: acct })}>Save</Button></div></Field>}
          <Field label={p.name === "cloudflare" ? "API token" : "API key"} hint={p.key_source === "env" ? "Set via backend/.env (takes precedence)." : "Stored on the backend only — never sent to the browser."}>
            <div className="flex gap-2">
              <div className="relative flex-1"><KeyRound className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input type="password" autoComplete="off" className="pl-9" value={key} onChange={(e) => setKey(e.target.value)} placeholder={p.has_key ? "•••••••• (saved)" : "Paste key"} /></div>
              <Button variant="outline" disabled={!key} onClick={async () => { await saveCfg({ api_key: key }, "Key saved"); setKey(""); }}>Save</Button>
              {p.has_key && p.key_source !== "env" && <Button variant="ghost" onClick={() => saveCfg({ api_key: "" }, "Key removed")}>Remove</Button>}
            </div>
          </Field>
        </div>
      )}
      {p.kinds.includes("text") && p.state !== "ineligible" && (
        <Field label="Text model" hint={p.default_text_model === "auto" ? "Leave on Default: Shelfcraft picks the best model your key can use right now, and switches automatically when the provider retires one (free models change often)."
          : `Default: ${p.default_text_model ?? "—"}`}>
          <div className="flex gap-2">
            {models.length ? <Select value={model} onChange={(e) => setModel(e.target.value)}><option value="">Default</option>{models.map((m) => <option key={m}>{m}</option>)}</Select>
              : <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder={p.default_text_model === "auto" ? "Automatic (recommended)" : p.default_text_model ?? ""} />}
            <Button variant="outline" onClick={() => saveCfg({ text_model: model })}>Save</Button>
          </div>
        </Field>
      )}
      {p.kinds.includes("image") && p.state !== "ineligible" && (
        <Field label="Image model" hint={`Default: ${p.default_image_model ?? "—"}`}>
          <div className="flex gap-2"><Input value={imgModel} onChange={(e) => setImgModel(e.target.value)} placeholder={p.default_image_model ?? ""} /><Button variant="outline" onClick={() => saveCfg({ image_model: imgModel })}>Save</Button></div>
        </Field>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={runTest} loading={testing} disabled={p.state === "ineligible"}>Test connection</Button>
        {test && <span className={`flex items-center gap-1 text-xs ${test.ok ? "text-success" : "text-danger"}`}>{test.ok ? <CircleCheck className="size-3.5" /> : <CircleAlert className="size-3.5" />}{test.detail}</span>}
      </div>
      {p.name === "ollama" && !p.configured && <Notice tone="warning" className="text-xs">Ollama isn&apos;t running. Start the Ollama app (or run <code>ollama serve</code>), then pull a model: <code>ollama pull qwen2.5:3b</code></Notice>}
      {p.name === "local_diffusion" && !p.configured && <Notice tone="warning" className="text-xs">Not installed. Run <code>{cmd.run("install-local-image-model")}</code> (downloads PyTorch CPU + ~2.5 GB model).</Notice>}
      <p className="text-[11.5px] text-muted"><b>Privacy:</b> {p.privacy_note}</p>
      {(p.last_error || p.last_success_at) && (
        <div className="border-t border-border pt-2 text-[11.5px] text-muted">
          {p.last_success_at && <span>Last success {timeAgo(p.last_success_at)}. </span>}
          {p.last_error && !(p.last_success_at && p.last_failure_at && new Date(p.last_success_at) > new Date(p.last_failure_at)) &&
            <span className="text-danger">Last error {timeAgo(p.last_failure_at)}: {p.last_error}</span>}
          {p.rate_limited_until && <span> · Rate-limited until {new Date(p.rate_limited_until).toLocaleTimeString()}</span>}
        </div>
      )}
    </Card>
  );
}

function PrefRow({ title, body, checked, onChange }: { title: string; body: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-start justify-between gap-4 border-b border-border py-3 last:border-0">
      <span><span className="block text-[13.5px] font-medium">{title}</span><span className="block text-[12.5px] text-muted">{body}</span></span>
      <Switch checked={checked} onChange={onChange} label={title} />
    </label>
  );
}

function NotificationPrefs() {
  const s = useSettings();
  const qc = useQueryClient();
  const [desktop, setDesktop] = React.useState(false);
  React.useEffect(() => { try { setDesktop(localStorage.getItem("shelfcraft-desktop-notify") === "1" && "Notification" in window && Notification.permission === "granted"); } catch { /* storage unavailable */ } }, []);
  if (!s.data) return <Skeleton className="h-48" />;
  const gd = s.data.generation_defaults as Record<string, unknown>;
  const n = (gd.notify ?? {}) as { success?: boolean; warning?: boolean };
  const save = async (next: { success?: boolean; warning?: boolean }) => {
    try { await patch("/settings", { generation_defaults: { ...gd, notify: { ...n, ...next } } }); qc.invalidateQueries({ queryKey: ["settings"] }); toast.success("Saved"); } catch (e) { toast.error((e as Error).message); }
  };
  const toggleDesktop = async (on: boolean) => {
    if (on) {
      if (!("Notification" in window)) return toast.error("This browser doesn't support desktop notifications.");
      const perm = await Notification.requestPermission();
      if (perm !== "granted") return toast.error("Notifications are blocked for this site in your browser settings.");
    }
    try { localStorage.setItem("shelfcraft-desktop-notify", on ? "1" : "0"); } catch { /* ignore */ }
    setDesktop(on);
  };
  return (
    <Card className="max-w-2xl p-5">
      <PrefRow title="Finished work" body="When listings, image sets, videos and Factory batches are ready." checked={n.success !== false} onChange={(v) => save({ success: v })} />
      <PrefRow title="Partial results" body="When a run finishes with some items failed." checked={n.warning !== false} onChange={(v) => save({ warning: v })} />
      <PrefRow title="Desktop notifications" body="Also pop up a Windows notification from this browser (works while the Shelfcraft tab is open)." checked={desktop} onChange={toggleDesktop} />
      <p className="pt-3 text-[12px] text-muted">Errors are always shown in the bell menu.</p>
    </Card>
  );
}

function Defaults() {
  const s = useSettings();
  const providers = useProviders();
  const qc = useQueryClient();
  const save = async (body: Record<string, unknown>) => { try { await patch("/settings", body); qc.invalidateQueries({ queryKey: ["settings"] }); toast.success("Saved"); } catch (e) { toast.error((e as Error).message); } };
  if (!s.data || !providers.data) return <Skeleton className="h-64" />;
  const order = s.data.fallback_order;
  const move = (i: number, d: number) => { const n = [...order]; const [x] = n.splice(i, 1); n.splice(i + d, 0, x); save({ fallback_order: n }); };
  const text = providers.data.filter((p) => p.kinds.includes("text") && p.state !== "ineligible" && !p.paid);
  const image = providers.data.filter((p) => p.kinds.includes("image") && p.state !== "ineligible" && !p.paid);
  const gd = s.data.generation_defaults as Record<string, string | number>;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="flex flex-col gap-4 p-5">
        <h3 className="text-[14.5px] font-semibold">Primary providers</h3>
        <Field label="Text (copy, research)"><Select value={s.data.default_text_provider} onChange={(e) => save({ default_text_provider: e.target.value })}>{text.map((p) => <option key={p.name} value={p.name}>{p.label} — {STATE[p.state].label}</option>)}</Select></Field>
        <Field label="Images (backgrounds, scenes)"><Select value={s.data.default_image_provider} onChange={(e) => save({ default_image_provider: e.target.value })}><option value="local_composite">None — non-AI backdrops only</option>{image.map((p) => <option key={p.name} value={p.name}>{p.label} — {STATE[p.state].label}</option>)}</Select></Field>
        <Field label="Default language"><Select value={String(gd.language ?? "en")} onChange={(e) => save({ generation_defaults: { ...gd, language: e.target.value } })}>{["en", "de", "fr", "es", "it", "hi", "ja", "pt"].map((l) => <option key={l}>{l}</option>)}</Select></Field>
      </Card>
      <Card className="flex flex-col gap-3 p-5">
        <h3 className="text-[14.5px] font-semibold">Free fallback order</h3>
        <p className="text-[12.5px] text-muted">If the primary provider fails or is rate-limited, these are tried in order, then local models. Only enabled, free-eligible providers are ever used.</p>
        {order.map((n, i) => {
          const p = providers.data!.find((x) => x.name === n);
          return (
            <div key={n} className="flex items-center gap-2 rounded-[10px] border border-border px-3 py-2 text-[13px]">
              <span className="w-5 font-mono text-xs text-muted">{i + 1}</span><span className="flex-1">{p?.label ?? n}</span>{p && <Badge tone={STATE[p.state].tone}>{STATE[p.state].label}</Badge>}
              <Button size="icon-sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></Button>
              <Button size="icon-sm" variant="ghost" aria-label="Move down" disabled={i === order.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
            </div>
          );
        })}
        <div className="rounded-[10px] border border-dashed border-border px-3 py-2 text-[12.5px] text-muted">Then: Ollama (local) · Local diffusion (local)</div>
      </Card>
    </div>
  );
}

function Usage() {
  const q = useApi<{ days: number; by_provider: { provider: string; kind: string; calls: number; succeeded: number; failed: number; input_tokens: number; output_tokens: number; avg_latency_ms: number; today: number }[] }>(["usage"], "/usage?days=30");
  if (q.isLoading) return <Skeleton className="h-48" />;
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead className="border-b border-border text-left text-xs text-muted"><tr>{["Provider", "Kind", "Calls (30d)", "Succeeded", "Failed", "Today", "Tokens in/out", "Avg latency"].map((h) => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}</tr></thead>
        <tbody>
          {!q.data?.by_provider.length && <tr><td colSpan={8} className="px-4 py-8 text-center text-muted">No AI calls recorded yet.</td></tr>}
          {q.data?.by_provider.map((u) => (
            <tr key={u.provider + u.kind} className="border-b border-border last:border-0">
              <td className="px-4 py-2.5 font-medium">{u.provider}</td><td className="px-4">{u.kind}</td><td className="px-4 tabular-nums">{u.calls}</td>
              <td className="px-4 tabular-nums text-success">{u.succeeded}</td><td className="px-4 tabular-nums text-danger">{u.failed}</td><td className="px-4 tabular-nums">{u.today}</td>
              <td className="px-4 tabular-nums">{u.input_tokens.toLocaleString()} / {u.output_tokens.toLocaleString()}</td><td className="px-4 tabular-nums">{(u.avg_latency_ms / 1000).toFixed(1)}s</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="border-t border-border px-4 py-2.5 text-xs text-muted">Counts are Shelfcraft&apos;s own records. Your provider dashboards are the source of truth for remaining free quota.</div>
    </Card>
  );
}

function Data() {
  const cmd = useScriptCommand();
  const storage = useApi<{ media: Record<string, number>; database_bytes: number; data_dir: string }>(["storage"], "/storage");
  const backups = useApi<{ name: string; size_bytes: number; created_at: string }[]>(["backups"], "/backups");
  const health = useApi<{ status: string; checks: Record<string, string | number> }>(["health"], "/health");
  const [busy, setBusy] = React.useState(false);
  const total = storage.data ? Object.values(storage.data.media).reduce((a, b) => a + b, 0) + storage.data.database_bytes : 0;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="flex flex-col gap-3 p-5">
        <h3 className="flex items-center gap-2 text-[14.5px] font-semibold"><HardDrive className="size-4" />Storage</h3>
        {storage.data ? (<>
          <div className="font-display text-2xl font-semibold">{formatBytes(total)}</div>
          <div className="text-xs text-muted break-all">Data folder: {storage.data.data_dir}</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
            <span className="text-muted">Database</span><span className="tabular-nums">{formatBytes(storage.data.database_bytes)}</span>
            {Object.entries(storage.data.media).map(([k, v]) => <React.Fragment key={k}><span className="capitalize text-muted">{k}</span><span className="tabular-nums">{formatBytes(v)}</span></React.Fragment>)}
          </div>
        </>) : <Skeleton className="h-24" />}
      </Card>
      <Card className="flex flex-col gap-3 p-5">
        <h3 className="flex items-center gap-2 text-[14.5px] font-semibold"><Database className="size-4" />System health</h3>
        {health.data ? Object.entries(health.data.checks).map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-[13px]"><span className="capitalize">{k.replace("_", " ")}</span><Badge tone={v === "ok" || (typeof v === "number" && v > 0) ? "success" : "warning"}>{String(v)}</Badge></div>
        )) : <Skeleton className="h-24" />}
      </Card>
      <Card className="flex flex-col gap-3 p-5 lg:col-span-2">
        <div className="flex items-center justify-between"><h3 className="text-[14.5px] font-semibold">Backups</h3>
          <Button loading={busy} onClick={async () => { setBusy(true); try { const r = await post<{ name: string }>("/backups"); toast.success(`Backup created: ${r.name}`); backups.refetch(); } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); } }}>Create backup now</Button></div>
        <p className="text-[12.5px] text-muted">A backup is a ZIP with a consistent copy of the database and all media. To restore, stop Shelfcraft and run <code>{cmd.run("restore", "-Backup <file>", "<file>")}</code> (see README).</p>
        {backups.data?.length ? backups.data.map((b) => (
          <div key={b.name} className="flex items-center justify-between rounded-[10px] border border-border px-3 py-2 text-[13px]"><span className="font-mono text-xs">{b.name}</span><span className="text-xs text-muted">{formatBytes(b.size_bytes)}</span>
            <Button size="sm" variant="outline" onClick={() => download(`/backups/${b.name}`)}>Download</Button></div>
        )) : <p className="text-[13px] text-muted">No backups yet.</p>}
      </Card>
    </div>
  );
}

function Prefs() {
  const s = useSettings();
  const qc = useQueryClient();
  const [name, setName] = React.useState("");
  const [token, setToken] = React.useState("");
  React.useEffect(() => { if (s.data) setName(s.data.display_name); try { setToken(localStorage.getItem("shelfcraft-token") ?? ""); } catch { /* ignore */ } }, [s.data]);
  return (
    <Card className="flex max-w-xl flex-col gap-4 p-5">
      <Field label="Display name"><div className="flex gap-2"><Input value={name} onChange={(e) => setName(e.target.value)} /><Button variant="outline" onClick={async () => { await patch("/settings", { display_name: name }); qc.invalidateQueries({ queryKey: ["settings"] }); toast.success("Saved"); }}>Save</Button></div></Field>
      <Field label="Access token (this browser)" hint="Only needed if you set SHELFCRAFT_ACCESS_TOKEN in backend/.env to protect the API on a shared computer.">
        <div className="flex gap-2"><Input type="password" value={token} onChange={(e) => setToken(e.target.value)} /><Button variant="outline" onClick={async () => {
          try { localStorage.setItem("shelfcraft-token", token); } catch { /* ignore */ }
          try { await get("/settings"); toast.success("Token works"); } catch { toast.error("Token rejected by the backend"); }
          qc.invalidateQueries();
        }}>Save</Button></div>
      </Field>
      <div className="text-[12.5px] text-muted">Theme can be changed from the sun/moon icon in the top bar.</div>
    </Card>
  );
}

export default function Page() {
  return <React.Suspense><SettingsInner /></React.Suspense>;
}
