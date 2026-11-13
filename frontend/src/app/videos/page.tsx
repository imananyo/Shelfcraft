"use client";
import { Clapperboard, Plus } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

export default function VideosPage() {
  const q = useApi<{ id: string; name: string; aspect: string; scenes: number; rendered: boolean; updated_at: string }[]>(["videos"], "/videos");
  return (
    <>
      <PageHeader title="Video creator" description="Product slideshow videos composed locally with FFmpeg — storyboard, text overlays, transitions and your own music. These are composed videos, not AI-generated video."
        actions={<Link href="/videos/new"><Button><Plus />New video</Button></Link>} />
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.isLoading ? <Skeleton className="h-48" /> : !q.data?.length ? (
        <EmptyState icon={<Clapperboard />} title="No videos yet" body="Pick a product and Shelfcraft builds a storyboard from its photos and creatives." action={<Link href="/videos/new"><Button><Plus />New video</Button></Link>} />
      ) : (
        <Card className="divide-y divide-border">
          {q.data.map((v) => (
            <Link key={v.id} href={`/videos/${v.id}`} className="flex items-center gap-4 px-5 py-3.5 hover:bg-sunken/60">
              <div className="flex size-9 items-center justify-center rounded-[9px] bg-primary-soft text-primary"><Clapperboard className="size-4" /></div>
              <div className="min-w-0 flex-1"><div className="truncate text-[13.5px] font-medium">{v.name}</div><div className="text-xs text-muted">{v.scenes} scenes · {timeAgo(v.updated_at)}</div></div>
              <Badge>{v.aspect}</Badge>{v.rendered ? <Badge tone="success">MP4 ready</Badge> : <Badge>Draft</Badge>}
            </Link>
          ))}
        </Card>
      )}
    </>
  );
}
