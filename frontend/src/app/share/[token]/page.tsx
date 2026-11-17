"use client";
import { Download } from "lucide-react";
import { useParams } from "next/navigation";
import * as React from "react";

type View = {
  title: string; kind: string; brand: string | null; created_at: string;
  items: { id: string; kind: string; title: string; url: string; thumb_url: string; ai: boolean }[];
  copy?: { title?: string; bullets?: string[]; description?: string } | null;
};

/** Public, read-only gallery for a share link (rendered without the app shell or sign-in). */
export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const [v, setV] = React.useState<View | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [zoom, setZoom] = React.useState<string | null>(null);
  React.useEffect(() => {
    fetch(`/api/share/${token}`).then(async (r) => {
      const d = await r.json().catch(() => null);
      if (!r.ok) throw new Error(d?.detail ?? "This link isn't available.");
      setV(d);
    }).catch((e) => setErr((e as Error).message));
  }, [token]);
  if (err) return <div className="grid min-h-full place-items-center p-6 text-center text-muted">{err}</div>;
  if (!v) return <div className="grid min-h-full place-items-center p-6 text-muted">Loading…</div>;
  return (
    <div className="min-h-full bg-background">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="mb-6">
          <div className="text-[12px] uppercase tracking-wide text-muted">{v.brand ? `${v.brand} · ` : ""}Shared {v.kind}</div>
          <h1 className="font-display text-2xl font-semibold">{v.title}</h1>
          <div className="text-[13px] text-muted">{v.items.length} visual{v.items.length === 1 ? "" : "s"} · view only</div>
        </div>
        {v.copy?.title && (
          <div className="mb-6 rounded-[14px] border border-border bg-card p-5 text-[14px]">
            <div className="mb-2 font-semibold">{v.copy.title}</div>
            {!!v.copy.bullets?.length && <ul className="mb-2 list-disc space-y-1 pl-5">{v.copy.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>}
            {v.copy.description && <p className="whitespace-pre-line text-muted">{v.copy.description}</p>}
          </div>
        )}
        {v.items.length === 0 && <div className="rounded-[14px] border border-dashed border-border p-10 text-center text-muted">No visuals in this project yet.</div>}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {v.items.map((it) => (
            <figure key={it.id} className="group overflow-hidden rounded-[14px] border border-border bg-card">
              {it.kind === "video"
                ? <video src={it.url} controls className="aspect-square w-full bg-black object-contain" />
                : <button type="button" onClick={() => setZoom(it.url)} className="block w-full"><img src={it.thumb_url} alt={it.title} className="aspect-square w-full bg-sunken object-contain" loading="lazy" /></button>}
              <figcaption className="flex items-center justify-between gap-2 px-3 py-2 text-[12px] text-muted">
                <span className="truncate">{it.title}{it.ai ? " · AI" : ""}</span>
                <a href={`${it.url}?download=1`} aria-label="Download" className="shrink-0 hover:text-foreground"><Download className="size-4" /></a>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
      {zoom && (
        <button type="button" onClick={() => setZoom(null)} className="fixed inset-0 z-50 grid place-items-center bg-black/80 p-4" aria-label="Close">
          <img src={zoom} alt="" className="max-h-full max-w-full object-contain" />
        </button>
      )}
    </div>
  );
}
