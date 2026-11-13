"use client";
import { Check, Palette, Plus } from "lucide-react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { activateBrand, useBrands, useSettings } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

export default function BrandsPage() {
  const q = useBrands();
  const s = useSettings();
  const qc = useQueryClient();
  return (
    <>
      <PageHeader title="Brands" description="Brand profiles are applied automatically to every generation — colors, fonts, voice, audience and guidelines."
        actions={<Link href="/brands/new"><Button><Plus />New brand</Button></Link>} />
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.isLoading ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-44" />)}</div>
        : q.data?.length === 0 ? (
          <EmptyState icon={<Palette />} title="Create your first brand" body="Add your logo, colors, fonts and tone of voice so every creative stays on-brand."
            action={<Link href="/brands/new"><Button><Plus />New brand</Button></Link>} />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {q.data?.map((b) => {
              const active = s.data?.active_brand_id === b.id;
              return (
                <Card key={b.id} className="flex flex-col overflow-hidden">
                  <div className="flex h-16">{(b.colors.length ? b.colors : ["#e7e5e4"]).map((c) => <div key={c} className="flex-1" style={{ background: c }} />)}</div>
                  <div className="flex flex-1 flex-col gap-3 p-4">
                    <div className="flex items-start gap-3">
                      <div className="-mt-10 flex size-14 items-center justify-center overflow-hidden rounded-[12px] border-2 border-surface bg-surface shadow-[var(--shadow-card)]">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        {b.logo_url ? <img src={b.logo_url} alt={`${b.name} logo`} className="size-full object-contain" /> : <span className="font-display text-xl font-semibold">{b.name[0]}</span>}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2"><h3 className="truncate text-[15px] font-semibold">{b.name}</h3>{active && <Badge tone="primary">Active</Badge>}</div>
                        <p className="line-clamp-2 text-[12.5px] text-muted">{b.tagline || b.tone_of_voice || "No tagline yet"}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {b.primary_font && <Badge>{b.primary_font}</Badge>}
                      <Badge>{b.product_count} product{b.product_count === 1 ? "" : "s"}</Badge>
                      {b.guidelines.length > 0 && <Badge>{b.guidelines.length} guideline doc{b.guidelines.length === 1 ? "" : "s"}</Badge>}
                    </div>
                    <div className="mt-auto flex items-center justify-between pt-1">
                      <span className="text-xs text-muted">Updated {timeAgo(b.updated_at)}</span>
                      <div className="flex gap-1.5">
                        {!active && <Button size="sm" variant="ghost" onClick={async () => { await activateBrand(b.id); qc.invalidateQueries({ queryKey: ["settings"] }); }}><Check />Use</Button>}
                        <Link href={`/brands/${b.id}`}><Button size="sm" variant="outline">Edit</Button></Link>
                      </div>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
    </>
  );
}
