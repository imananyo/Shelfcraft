"use client";
import Link from "next/link";
import { PageHeader } from "@/components/ui/misc";
import { BrandForm } from "../brand-form";

export default function NewBrandPage() {
  return (
    <>
      <PageHeader eyebrow={<Link href="/brands" className="hover:text-foreground">Brands</Link>} title="New brand" description="Set up the identity Shelfcraft uses for every listing, image and video." />
      <BrandForm />
    </>
  );
}
