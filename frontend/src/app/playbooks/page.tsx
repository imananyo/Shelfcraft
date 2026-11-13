"use client";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, Download, Plus, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/misc";
import { Dialog } from "@/components/ui/overlay";
import { post } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { timeAgo } from "@/lib/utils";

interface PlaybookT { id: string; name: string; description?: string; category: string; steps: Record<string, unknown>[]; settings: Record<string, unknown>; is_template: boolean; updated_at: string }

export default function PlaybooksPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const mine = useApi<PlaybookT[]>(["playbooks"], "/playbooks");
  const lib = useApi<PlaybookT[]>(["playbooks", "templates"], "/playbooks?templates=true");
  const [libOpen, setLibOpen] = React.useState(false);
  const imp = async (id: string) => {
    const p = await post<PlaybookT>(`/playbooks/${id}/import`);
    qc.invalidateQueries({ queryKey: ["playbooks"] });
    toast.success("Imported — customize and run it");
    router.push(`/playbooks/${p.id}`);
  };
  const create = async () => {
    const p = await post<PlaybookT>("/playbooks", { name: "New playbook", steps: [{ kind: "creative", creative_type: "white_bg_main" }] });
    router.push(`/playbooks/${p.id}`);
  };
  return (
    <>
      <PageHeader title="Playbooks" description="Reusable recipes: a sequence of generation steps you can run on any product, or on many at once."
        actions={<><Button variant="outline" onClick={() => setLibOpen(true)}><BookOpen />Playbook templates</Button><Button onClick={create}><Plus />New playbook</Button></>} />
      {mine.isLoading ? <Skeleton className="h-40" /> : !mine.data?.length ? (
        <EmptyState icon={<Workflow />} title="No playbooks yet" body="Start from a playbook template or create from scratch."
          action={<div className="flex gap-2"><Button variant="outline" onClick={() => setLibOpen(true)}>Playbook templates</Button><Button onClick={create}>New playbook</Button></div>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {mine.data.map((p) => (
            <Link key={p.id} href={`/playbooks/${p.id}`}>
              <Card className="h-full p-4 transition hover:border-border-strong">
                <div className="flex items-center justify-between"><h3 className="text-[15px] font-semibold">{p.name}</h3><Badge className="capitalize">{p.category}</Badge></div>
                <p className="mt-1 line-clamp-2 text-[12.5px] text-muted">{p.description || "No description"}</p>
                <div className="mt-3 flex flex-wrap gap-1">{p.steps.slice(0, 6).map((s, i) => <Badge key={i}>{String(s.creative_type ?? s.kind).replace("_", " ")}</Badge>)}</div>
                <div className="mt-3 text-[11px] text-muted">{p.steps.length} steps · updated {timeAgo(p.updated_at)}</div>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <Dialog open={libOpen} onOpenChange={setLibOpen} title="Playbook templates" wide description="Import a template to make your own editable copy.">
        <div className="grid gap-3 sm:grid-cols-2">
          {lib.data?.map((t) => (
            <Card key={t.id} className="flex flex-col p-4">
              <div className="flex items-center justify-between"><h3 className="text-[14px] font-semibold">{t.name}</h3><Badge className="capitalize">{t.category}</Badge></div>
              <p className="mt-1 flex-1 text-[12.5px] text-muted">{t.description}</p>
              <div className="mt-2 flex flex-wrap gap-1">{t.steps.map((s, i) => <Badge key={i}>{String(s.creative_type ?? s.kind).replace("_", " ")}</Badge>)}</div>
              <Button className="mt-3 w-fit" size="sm" onClick={() => imp(t.id)}><Download />Import</Button>
            </Card>
          ))}
        </div>
      </Dialog>
    </>
  );
}
