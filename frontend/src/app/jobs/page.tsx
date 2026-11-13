"use client";
import { ListChecks, RefreshCw, Square } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import { JobStatusBadge } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Card, EmptyState, ErrorState, PageHeader, Progress, Skeleton } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Job } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

const FILTERS = [["", "All"], ["queued,running", "Active"], ["succeeded", "Done"], ["failed", "Failed"], ["cancelled", "Cancelled"]];

export default function JobsPage() {
  const [status, setStatus] = React.useState("");
  const q = useApi<{ items: Job[]; counts: Record<string, number> }>(["jobs", "page", status], `/jobs?limit=200${status ? `&status=${status}` : ""}`, { refetchInterval: 2000 });
  const act = async (id: string, what: "retry" | "cancel") => {
    try { await post(`/jobs/${id}/${what}`); q.refetch(); } catch (e) { toast.error((e as Error).message); }
  };
  return (
    <>
      <PageHeader title="Jobs" description="Every long-running generation is a persistent job. Jobs survive restarts, retry automatically with backoff (up to 3 attempts), and can be cancelled or retried here." />
      <div className="mb-4 flex flex-wrap gap-1.5">
        {FILTERS.map(([v, l]) => (
          <button key={v} onClick={() => setStatus(v)} className={cn("rounded-full border px-3 py-1 text-[12.5px] font-medium", status === v ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-sunken")}>
            {l}{v && q.data ? ` · ${v.split(",").reduce((a, s) => a + (q.data!.counts[s] ?? 0), 0)}` : ""}
          </button>
        ))}
      </div>
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.isLoading ? <Skeleton className="h-64" /> : !q.data?.items.length ? <EmptyState icon={<ListChecks />} title="No jobs" body="Generations, edits, renders and bulk runs show up here." /> : (
        <Card className="divide-y divide-border">
          {q.data.items.map((j) => (
            <div key={j.id} className="flex flex-wrap items-center gap-4 px-5 py-3">
              <div className="min-w-48 flex-1">
                <div className="flex items-center gap-2 text-[13.5px] font-medium">{j.label}<JobStatusBadge status={j.status} /></div>
                <div className="mt-0.5 truncate text-xs text-muted">{j.status === "failed" ? j.error : j.message} {String(j.payload_summary.product_name ?? j.payload_summary.title ?? "")}</div>
              </div>
              {j.status === "running" && <Progress value={j.progress} tone="ai" className="w-40" />}
              <div className="text-xs text-muted">{j.attempts > 0 && `attempt ${j.attempts}/${j.max_attempts} · `}{timeAgo(j.created_at)}</div>
              {(j.status === "queued" || j.status === "running") && <Button size="sm" variant="ghost" onClick={() => act(j.id, "cancel")}><Square />Cancel</Button>}
              {(j.status === "failed" || j.status === "cancelled") && <Button size="sm" variant="outline" onClick={() => act(j.id, "retry")}><RefreshCw />Retry</Button>}
            </div>
          ))}
        </Card>
      )}
    </>
  );
}
