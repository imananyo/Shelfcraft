"use client";
import { Boxes, FileText, Gauge, Layers, PenLine } from "lucide-react";
import { OptionCard, PageHeader } from "@/components/ui/misc";

export default function LabsPage() {
  return (
    <>
      <PageHeader title="Labs" description="Focused tools for specific jobs." />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <OptionCard icon={<FileText />} title="Title & Bullets" description="Title, item highlights and bullet points — single or bulk" href="/labs/title-bullets" />
        <OptionCard icon={<Boxes />} title="Packaging Idea Generator" description="Up to 15 packaging concepts, with optional AI mock-ups" href="/labs/packaging" />
        <OptionCard icon={<PenLine />} title="Projects" description="Create a design from scratch" href="/projects?new=1" />
        <OptionCard icon={<Gauge />} title="Listing Grader" description="Score any listing and get concrete fixes" href="/grader" />
        <OptionCard icon={<Layers />} title="Image → Layers" description="Split a flat image into editable background, product and text" href="/library?decompose=1" />
      </div>
    </>
  );
}
