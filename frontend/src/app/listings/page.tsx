"use client";
import { FileText, Plus } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

interface Row { id: string; name: string; marketplace: string; product_name?: string; has_copy: boolean; image_count: number; updated_at: string }

export default function ListingsPage() {
  const q = useApi<Row[]>(["listings"], "/listings");
  return (
    <>
      <PageHeader title="Listing builder" description="Marketplace-ready copy and image sets, grounded in your product data. Edit, regenerate field by field, and export."
        actions={<Link href="/listings/new"><Button><Plus />New listing</Button></Link>} />
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.isLoading ? <Skeleton className="h-64" /> : !q.data?.length ? (
        <EmptyState icon={<FileText />} title="No listings yet" body="Pick a product and marketplace — Shelfcraft writes the title, bullets, description and search terms, then builds the image set."
          action={<Link href="/listings/new"><Button><Plus />New listing</Button></Link>} />
      ) : (
        <Card className="divide-y divide-border">
          {q.data.map((r) => (
            <Link key={r.id} href={`/listings/${r.id}`} className="flex items-center gap-4 px-5 py-3.5 hover:bg-sunken/60">
              <div className="flex size-9 items-center justify-center rounded-[9px] bg-primary-soft text-primary"><FileText className="size-4" /></div>
              <div className="min-w-0 flex-1"><div className="truncate text-[13.5px] font-medium">{r.name}</div><div className="text-xs text-muted">{r.product_name} · {timeAgo(r.updated_at)}</div></div>
              <Badge className="capitalize">{r.marketplace}</Badge>
              {r.has_copy ? <Badge tone="success">Copy ready</Badge> : <Badge>Draft</Badge>}
              <Badge>{r.image_count} images</Badge>
            </Link>
          ))}
        </Card>
      )}
    </>
  );
}
