"use client";
import { useQueryClient } from "@tanstack/react-query";
import { Copy, KeyRound, Plug, ShieldCheck, Trash2, UserPlus, Users } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/shell/auth-gate";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch } from "@/components/ui/form";
import { Badge, Card, Notice } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { del, patch, post } from "@/lib/api";
import { useApi, useCapabilities } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

const copy = async (text: string, what = "Copied") => { await navigator.clipboard.writeText(text); toast.success(what); };

// ---------------------------------------------------------------- Team
interface MemberT { id: string; name: string; email: string; role: string; status: string; last_login_at?: string; created_at: string }

export function TeamTab() {
  const auth = useAuth();
  const qc = useQueryClient();
  const members = useApi<MemberT[]>(["members"], "/members");
  const [setup, setSetup] = React.useState({ name: "", email: "", password: "" });
  const [inv, setInv] = React.useState({ email: "", role: "editor" });
  const [link, setLink] = React.useState<string | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["members"] }); qc.invalidateQueries({ queryKey: ["auth"] }); };
  if (!auth.data) return null;
  if (!auth.data.team_mode) {
    return (
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="flex flex-col gap-3 p-5">
          <h3 className="flex items-center gap-2 text-[15px] font-semibold"><Users className="size-4" />Set up your team</h3>
          <p className="text-[13px] text-muted">Create the owner account. After this, everyone (including you) signs in, and you can invite teammates as admins, editors or viewers.</p>
          <Field label="Your name"><Input value={setup.name} onChange={(e) => setSetup({ ...setup, name: e.target.value })} /></Field>
          <Field label="Email"><Input type="email" value={setup.email} onChange={(e) => setSetup({ ...setup, email: e.target.value })} /></Field>
          <Field label="Password" hint="At least 8 characters"><Input type="password" autoComplete="new-password" value={setup.password} onChange={(e) => setSetup({ ...setup, password: e.target.value })} /></Field>
          <Button onClick={async () => { try { await post("/auth/setup", setup); toast.success("Team enabled — you're the owner"); refresh(); } catch (e) { toast.error((e as Error).message); } }}><ShieldCheck />Enable team mode</Button>
        </Card>
        <Notice>
          <b>How teammates reach Shelfcraft.</b> By default Shelfcraft only accepts connections from this computer. To let teammates on your network join,
          start it with <code>scripts\start.ps1 -Prod -Lan</code> after enabling team mode, and share <code>http://&lt;this-PC&apos;s-IP&gt;:3000</code> plus their invite link.
          Shelfcraft doesn&apos;t send emails — you share invite links yourself.
        </Notice>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <Card className="flex flex-wrap items-end gap-3 p-5">
        <Field label="Invite by email" className="min-w-60 flex-1"><Input type="email" value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} placeholder="teammate@company.com" /></Field>
        <Field label="Role" className="w-36"><Select value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })}><option value="admin">Admin</option><option value="editor">Editor</option><option value="viewer">Viewer</option></Select></Field>
        <Button onClick={async () => { try { const r = await post<{ invite_path: string }>("/members", inv); setLink(`${window.location.origin}${r.invite_path}`); setInv({ email: "", role: "editor" }); refresh(); } catch (e) { toast.error((e as Error).message); } }}><UserPlus />Create invite</Button>
      </Card>
      <Card className="divide-y divide-border">
        {members.data?.map((m) => (
          <div key={m.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-[13px]">
            <div className="flex size-8 items-center justify-center rounded-full bg-sunken text-xs font-semibold">{m.name.slice(0, 2).toUpperCase()}</div>
            <div className="min-w-0 flex-1"><div className="font-medium">{m.name} <span className="font-normal text-muted">· {m.email}</span></div>
              <div className="text-xs text-muted">{m.status === "invited" ? "Invite pending" : m.last_login_at ? `Last active ${timeAgo(m.last_login_at)}` : "Never signed in"}</div></div>
            <Badge tone={m.status === "active" ? "success" : m.status === "invited" ? "warning" : "neutral"}>{m.status}</Badge>
            {m.role === "owner" ? <Badge tone="primary">owner</Badge> : (
              <>
                <Select className="h-8 w-28 text-[12.5px]" value={m.role} onChange={async (e) => { await patch(`/members/${m.id}`, { role: e.target.value }); refresh(); }} aria-label="Role">
                  <option value="admin">Admin</option><option value="editor">Editor</option><option value="viewer">Viewer</option></Select>
                <Button size="sm" variant="ghost" onClick={async () => { await patch(`/members/${m.id}`, { status: m.status === "disabled" ? "active" : "disabled" }); refresh(); }}>{m.status === "disabled" ? "Enable" : "Disable"}</Button>
              </>
            )}
          </div>
        ))}
      </Card>
      <Notice className="text-xs"><b>Roles:</b> Owner & Admin manage members · Editor creates and edits everything · Viewer can look and download but not change anything.</Notice>
      <Dialog open={!!link} onOpenChange={(o) => !o && setLink(null)} title="Share this invite link" description="Valid for 7 days, single use. Shelfcraft doesn't send emails."
        footer={<Button onClick={() => link && copy(link, "Invite link copied")}><Copy />Copy link</Button>}>
        <div className="break-all rounded-[10px] bg-sunken p-3 font-mono text-[12px]">{link}</div>
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------- API & MCP
interface KeyT { id: string; name: string; prefix: string; scopes: string[]; created_at: string; last_used_at?: string; request_count: number; revoked: boolean }

export function ApiTab() {
  const keys = useApi<KeyT[]>(["api-keys"], "/api-keys");
  const [name, setName] = React.useState("My integration");
  const [write, setWrite] = React.useState(true);
  const [created, setCreated] = React.useState<string | null>(null);
  const api = typeof window !== "undefined" ? `${window.location.protocol}//${window.location.hostname}:8000` : "http://127.0.0.1:8000";
  const caps = useCapabilities();
  const mcpJson = JSON.stringify({ mcpServers: { shelfcraft: {
    command: caps.data?.mcp?.command ?? "<shelfcraft>/backend/.venv/bin/python",
    args: [caps.data?.mcp?.script ?? "<shelfcraft>/backend/mcp_server.py"],
    env: { SHELFCRAFT_API_KEY: created ?? "sk_shelf_…", SHELFCRAFT_API_URL: "http://127.0.0.1:8000" } } } }, null, 2);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <Card className="flex flex-col gap-3 p-5">
          <h3 className="flex items-center gap-2 text-[15px] font-semibold"><KeyRound className="size-4" />API keys</h3>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Name" className="min-w-48 flex-1"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <label className="mb-2 flex items-center gap-2 text-[13px]"><Switch checked={write} onChange={setWrite} label="Write access" />Write access</label>
            <Button onClick={async () => { const r = await post<{ key: string }>("/api-keys", { name, scopes: write ? ["read", "write"] : ["read"] }); setCreated(r.key); keys.refetch(); }}>Create key</Button>
          </div>
          {created && (
            <Notice tone="success"><div className="mb-1 font-medium">Copy your key now — it won&apos;t be shown again.</div>
              <div className="flex items-center gap-2"><code className="flex-1 break-all text-[12px]">{created}</code><Button size="sm" variant="outline" onClick={() => copy(created, "Key copied")}><Copy />Copy</Button></div></Notice>
          )}
          {keys.data?.map((k) => (
            <div key={k.id} className="flex items-center gap-3 rounded-[10px] border border-border px-3 py-2 text-[13px]">
              <div className="min-w-0 flex-1"><div className="font-medium">{k.name} <code className="text-xs text-muted">{k.prefix}…</code></div>
                <div className="text-xs text-muted">{k.scopes.join(" + ")} · {k.request_count} requests{k.last_used_at ? ` · last used ${timeAgo(k.last_used_at)}` : ""}</div></div>
              {k.revoked ? <Badge>revoked</Badge> : <Button size="icon-sm" variant="ghost" aria-label="Revoke key" onClick={async () => { await del(`/api-keys/${k.id}`); keys.refetch(); toast.success("Key revoked"); }}><Trash2 /></Button>}
            </div>
          ))}
        </Card>
        <Card className="flex flex-col gap-2 p-5 text-[13px]">
          <h3 className="text-[15px] font-semibold">Public API</h3>
          <p className="text-muted">REST API at <code>{api}/v1</code> with interactive docs at <a className="text-primary underline" href={`${api}/v1/docs`} target="_blank" rel="noreferrer">{api}/v1/docs</a>. 120 requests/minute per key. The app&apos;s own local API (<code>/api</code>) is unchanged.</p>
          <pre className="overflow-x-auto rounded-[10px] bg-sunken p-3 text-[11.5px]">{`curl -H "Authorization: Bearer sk_shelf_…" ${api}/v1/products`}</pre>
          <Notice className="text-xs">The API listens on this computer only. To use it from elsewhere, run Shelfcraft with <code>-Lan</code> (team mode required) or put it behind your own secure tunnel — never expose it without a key.</Notice>
        </Card>
      </div>
      <Card className="flex flex-col gap-3 p-5 text-[13px]">
        <h3 className="flex items-center gap-2 text-[15px] font-semibold"><Plug className="size-4" />MCP server</h3>
        <p className="text-muted">Let AI assistants that support the Model Context Protocol (e.g. Claude Desktop, Claude Code) use Shelfcraft: search products, create and grade listings, generate images, track jobs. It uses an API key, so it has exactly that key&apos;s permissions.</p>
        <div className="font-medium">Claude Desktop / most MCP clients — add to the config file:</div>
        <pre className="max-h-72 overflow-auto rounded-[10px] bg-sunken p-3 text-[11.5px]">{mcpJson}</pre>
        <Button size="sm" variant="outline" className="w-fit" onClick={() => copy(mcpJson, "MCP config copied")}><Copy />Copy config</Button>
        <div className="font-medium">Claude Code:</div>
        <pre className="overflow-x-auto rounded-[10px] bg-sunken p-3 text-[11.5px]">{`claude mcp add shelfcraft -e SHELFCRAFT_API_KEY=${created ?? "sk_shelf_…"} -- "C:\\Users\\dutta\\Desktop\\shelfcraft1\\backend\\.venv\\Scripts\\python.exe" "C:\\Users\\dutta\\Desktop\\shelfcraft1\\backend\\mcp_server.py"`}</pre>
        <p className="text-xs text-muted">Tools: list_brands, list_products, get_product, create_product, create_listing, get_listing, translate_listing, grade_listing, generate_creative, get_job, wait_for_job, get_asset. Shelfcraft must be running.</p>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- Integrations
interface Spapi { enabled: boolean; has_client_id: boolean; has_client_secret: boolean; has_refresh_token: boolean; last_error?: string; last_success_at?: string; marketplaces: string[]; note: string }

export function IntegrationsTab() {
  const q = useApi<Spapi>(["spapi"], "/integrations/amazon");
  const [f, setF] = React.useState({ client_id: "", client_secret: "", refresh_token: "" });
  const save = async (body: Record<string, unknown>) => { try { await patch("/integrations/amazon", body); q.refetch(); toast.success("Saved"); } catch (e) { toast.error((e as Error).message); } };
  const s = q.data;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="flex flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <div><h3 className="text-[15px] font-semibold">Amazon Selling Partner API</h3><p className="text-[12.5px] text-muted">{s?.note}</p></div>
          {s && <Switch checked={s.enabled} onChange={(v) => save({ enabled: v })} label="Enable Amazon connector" />}
        </div>
        <Field label="LWA client ID" hint={s?.has_client_id ? "saved" : undefined}><Input value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })} placeholder={s?.has_client_id ? "•••••• (saved)" : "amzn1.application-oa2-client…"} /></Field>
        <Field label="LWA client secret" hint={s?.has_client_secret ? "saved" : undefined}><Input type="password" value={f.client_secret} onChange={(e) => setF({ ...f, client_secret: e.target.value })} placeholder={s?.has_client_secret ? "•••••• (saved)" : ""} /></Field>
        <Field label="Refresh token" hint={s?.has_refresh_token ? "saved" : undefined}><Input type="password" value={f.refresh_token} onChange={(e) => setF({ ...f, refresh_token: e.target.value })} placeholder={s?.has_refresh_token ? "•••••• (saved)" : "Atzr|…"} /></Field>
        <Button className="w-fit" disabled={!f.client_id && !f.client_secret && !f.refresh_token} onClick={() => { save(Object.fromEntries(Object.entries(f).filter(([, v]) => v))); setF({ client_id: "", client_secret: "", refresh_token: "" }); }}>Save credentials</Button>
        {s?.last_error && <Notice tone="danger" className="text-xs">Last error: {s.last_error}</Notice>}
      </Card>
      <Notice>
        <b>How to get credentials:</b> in Seller Central, register as a developer for your own account, create a private SP-API app,
        then authorize it to get a refresh token. With it enabled, <b>Products → Add product → Import from Amazon</b> pulls your listing&apos;s title, bullets,
        description and images by ASIN via the official Catalog Items API. Marketplaces: {s?.marketplaces.join(", ")}.
        <div className="mt-2">Without an Amazon account you can still <b>paste</b> any listing text — Shelfcraft parses it into a product.</div>
      </Notice>
    </div>
  );
}

