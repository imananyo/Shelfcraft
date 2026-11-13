"use client";
import { LayoutTemplate, Plus } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

export default function AplusList() {
  const q = useApi<{ id: string; name: string; tier: string; module_count: number; updated_at: string }[]>(["aplus"], "/aplus");
  return (
    <>
      <PageHeader title="A+ content" description="Build Basic, Premium or Premium-mobile A+ layouts from editable modules. Reorder by dragging, edit every layer, export a ready-to-upload ZIP."
        actions={<Link href="/aplus/new"><Button><Plus />New A+ layout</Button></Link>} />
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.isLoading ? <Skeleton className="h-48" /> : !q.data?.length ? (
        <EmptyState icon={<LayoutTemplate />} title="No A+ layouts yet" body="Pick a product and the modules you need — hero banner, feature row, comparison, brand story and more."
          action={<Link href="/aplus/new"><Button><Plus />New A+ layout</Button></Link>} />
      ) : (
        <Card className="divide-y divide-border">
          {q.data.map((p) => (
            <Link key={p.id} href={`/aplus/${p.id}`} className="flex items-center gap-4 px-5 py-3.5 hover:bg-sunken/60">
              <div className="flex size-9 items-center justify-center rounded-[9px] bg-primary-soft text-primary"><LayoutTemplate className="size-4" /></div>
              <div className="min-w-0 flex-1"><div className="truncate text-[13.5px] font-medium">{p.name}</div><div className="text-xs text-muted">{timeAgo(p.updated_at)}</div></div>
              <Badge className="capitalize">{p.tier}</Badge><Badge>{p.module_count} modules</Badge>
            </Link>
          ))}
        </Card>
      )}
    </>
  );
}
