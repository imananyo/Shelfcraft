"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ErrorState, PageHeader, Skeleton } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import type { Brand } from "@/lib/types";
import { BrandForm } from "../brand-form";

export default function EditBrandPage() {
  const { id } = useParams<{ id: string }>();
  const q = useApi<Brand>(["brand", id], `/brands/${id}`);
  return (
    <>
      <PageHeader eyebrow={<Link href="/brands" className="hover:text-foreground">Brands</Link>} title={q.data?.name ?? "Brand"} description="Changes apply to all future generations." />
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data ? <BrandForm key={q.data.id} brand={q.data} /> : <Skeleton className="h-96" />}
    </>
  );
}
