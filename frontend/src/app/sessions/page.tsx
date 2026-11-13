"use client";
import { History, Search } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { ImageThumb } from "@/components/shared";
import { Input } from "@/components/ui/form";
import { Badge, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

interface Row { id: string; name: string; kind: string; thumb_url?: string; updated_at: string }
const HREF: Record<string, (id: string) => string> = {
  listing: (id) => `/listings/${id}`, aplus: (id) => `/aplus/${id}`, video: (id) => `/videos/${id}`, ads: (id) => `/ads/${id}`,
  packaging: (id) => `/labs/packaging?project=${id}`,
};

export default function RecentWork() {
  const [q, setQ] = React.useState("");
  const list = useApi<Row[]>(["projects", "recent", q], `/projects${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  return (
    <>
      <PageHeader title="Recent work" description="Everything you've made — listings, designs, A+, videos, ads and packaging ideas." />
      <div className="relative mb-4 max-w-md"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" /><Input className="pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search sessions…" /></div>
      {list.isLoading ? <Skeleton className="h-64" /> : !list.data?.length ? (
        <EmptyState icon={<History />} title="No sessions yet" body="Generate your first listing visuals and they will show up here." action={<Link href="/create" className="text-[13px] font-medium text-primary hover:underline">Start creating →</Link>} />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {list.data.map((p) => (
            <Link key={p.id} href={(HREF[p.kind] ?? ((id: string) => `/projects/${id}`))(p.id)}>
              <Card className="overflow-hidden transition hover:border-border-strong">
                <ImageThumb src={p.thumb_url} alt={p.name} className="aspect-[4/3] rounded-none border-0 [&_img]:object-contain" />
                <div className="p-3"><div className="truncate text-[13px] font-medium">{p.name}</div>
                  <div className="mt-1 flex items-center justify-between"><Badge className="capitalize">{p.kind}</Badge><span className="text-[11px] text-muted">{timeAgo(p.updated_at)}</span></div></div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
