"use client";
import { Megaphone, Plus } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

export default function AdsList() {
  const q = useApi<{ id: string; name: string; format: string; concepts: number; updated_at: string }[]>(["ads"], "/ads");
  return (
    <>
      <PageHeader title="Ads studio" description="Brainstorm ad concepts per persona, then render A/B variants as editable creatives or short videos."
        actions={<Link href="/ads/new"><Button><Plus />New ad set</Button></Link>} />
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.isLoading ? <Skeleton className="h-40" /> : !q.data?.length ? (
        <EmptyState icon={<Megaphone />} title="No ad sets yet" body="Pick a product and format; Shelfcraft proposes concepts you can test against each other." action={<Link href="/ads/new"><Button><Plus />New ad set</Button></Link>} />
      ) : (
        <Card className="divide-y divide-border">
          {q.data.map((a) => (
            <Link key={a.id} href={`/ads/${a.id}`} className="flex items-center gap-4 px-5 py-3.5 hover:bg-sunken/60">
              <div className="flex size-9 items-center justify-center rounded-[9px] bg-primary-soft text-primary"><Megaphone className="size-4" /></div>
              <div className="min-w-0 flex-1"><div className="truncate text-[13.5px] font-medium">{a.name}</div><div className="text-xs text-muted">{timeAgo(a.updated_at)}</div></div>
              <Badge>{a.format}</Badge><Badge>{a.concepts} concepts</Badge>
            </Link>
          ))}
        </Card>
      )}
    </>
  );
}
