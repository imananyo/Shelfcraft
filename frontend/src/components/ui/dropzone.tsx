"use client";
import { Upload } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export function Dropzone({ onFiles, accept = "image/*", multiple = true, label = "Drop images here or click to upload", hint, className, compact, disabled }: {
  onFiles: (files: File[]) => void; accept?: string; multiple?: boolean; label?: string; hint?: string; className?: string; compact?: boolean; disabled?: boolean;
}) {
  const [over, setOver] = React.useState(false);
  const input = React.useRef<HTMLInputElement>(null);
  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      onClick={() => !disabled && input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (disabled) return;
        const files = Array.from(e.dataTransfer.files);
        if (files.length) onFiles(multiple ? files : files.slice(0, 1));
      }}
      className={cn("flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-[14px] border border-dashed border-border-strong bg-surface text-center transition-colors hover:border-primary hover:bg-primary-soft/40",
        over && "border-primary bg-primary-soft/60", compact ? "px-4 py-5" : "px-6 py-10", disabled && "pointer-events-none opacity-50", className)}
    >
      <div className="flex size-9 items-center justify-center rounded-full bg-sunken text-muted"><Upload className="size-4" /></div>
      <div className="text-[13.5px] font-medium">{label}</div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
      <input ref={input} type="file" accept={accept} multiple={multiple} className="hidden"
        onChange={(e) => { const f = Array.from(e.target.files ?? []); if (f.length) onFiles(f); e.target.value = ""; }} />
    </div>
  );
}
