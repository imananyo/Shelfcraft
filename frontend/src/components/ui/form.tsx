"use client";
import { Plus, X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

const field = "w-full rounded-[10px] border border-border-strong bg-surface px-3 text-[13.5px] text-foreground placeholder:text-muted/80 transition-colors focus:border-primary focus:outline-none focus:ring-3 focus:ring-[var(--ring)] disabled:opacity-60";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => <input ref={ref} className={cn(field, "h-9", className)} {...p} />,
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, rows = 3, ...p }, ref) => <textarea ref={ref} rows={rows} className={cn(field, "py-2 leading-relaxed resize-y", className)} {...p} />,
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...p }, ref) => (
    <select ref={ref} className={cn(field, "h-9 pr-8 appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%23888%22 stroke-width=%222%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[right_10px_center] bg-no-repeat", className)} {...p}>
      {children}
    </select>
  ),
);
Select.displayName = "Select";

export function Label({ className, ...p }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-[13px] font-medium text-foreground", className)} {...p} />;
}

export function Field({ label, hint, error, children, className, htmlFor, aside }: {
  label?: React.ReactNode; hint?: React.ReactNode; error?: string | null; children: React.ReactNode; className?: string; htmlFor?: string; aside?: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {(label || aside) && (
        <div className="flex items-baseline justify-between gap-2">
          {label && <Label htmlFor={htmlFor}>{label}</Label>}
          {aside && <span className="text-xs text-muted">{aside}</span>}
        </div>
      )}
      {children}
      {error ? <p className="text-xs text-danger">{error}</p> : hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

/** Chips input: Enter or comma adds, Backspace on empty removes last. */
export function ChipsInput({ value, onChange, max = 6, placeholder }: { value: string[]; onChange: (v: string[]) => void; max?: number; placeholder?: string }) {
  const [draft, setDraft] = React.useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !value.includes(v) && value.length < max) onChange([...value, v]);
    setDraft("");
  };
  return (
    <div className={cn(field, "flex min-h-9 flex-wrap items-center gap-1.5 py-1.5")}>
      {value.map((chip) => (
        <span key={chip} className="inline-flex items-center gap-1 rounded-full bg-primary-soft px-2.5 py-0.5 text-xs font-medium text-primary">
          {chip}
          <button type="button" aria-label={`Remove ${chip}`} onClick={() => onChange(value.filter((c) => c !== chip))} className="opacity-70 hover:opacity-100">
            <X className="size-3" />
          </button>
        </span>
      ))}
      {value.length < max && (
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
            else if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
          }}
          onBlur={add}
          placeholder={value.length ? "" : placeholder}
          className="min-w-24 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-muted/80"
        />
      )}
      <span className="ml-auto text-[11px] text-muted">{value.length}/{max}</span>
    </div>
  );
}

/** List editor for string arrays (features, bullets). */
export function ListInput({ value, onChange, placeholder, max = 30, multiline }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; max?: number; multiline?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      {value.map((item, i) => (
        <div key={i} className="flex items-start gap-2">
          {multiline ? (
            <Textarea rows={2} value={item} placeholder={placeholder} onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))} />
          ) : (
            <Input value={item} placeholder={placeholder} onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))} />
          )}
          <button type="button" aria-label="Remove item" className="mt-2 text-muted hover:text-danger" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            <X className="size-4" />
          </button>
        </div>
      ))}
      {value.length < max && (
        <button type="button" onClick={() => onChange([...value, ""])} className="inline-flex w-fit items-center gap-1.5 text-[13px] font-medium text-primary hover:underline">
          <Plus className="size-3.5" /> Add
        </button>
      )}
    </div>
  );
}

export function ColorSwatches({ value, onChange, max = 4 }: { value: string[]; onChange: (v: string[]) => void; max?: number }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {value.map((c, i) => (
        <div key={i} className="group relative">
          <label className="block size-11 cursor-pointer overflow-hidden rounded-[10px] border border-border-strong shadow-[var(--shadow-card)]" style={{ background: c }} title={c}>
            <input type="color" className="sr-only" value={c} onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))} aria-label={`Brand color ${i + 1}`} />
          </label>
          <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))} aria-label="Remove color"
            className="absolute -right-1.5 -top-1.5 hidden size-5 items-center justify-center rounded-full border border-border bg-surface text-muted shadow group-hover:flex">
            <X className="size-3" />
          </button>
          <div className="mt-1 text-center font-mono text-[10px] text-muted">{c}</div>
        </div>
      ))}
      {value.length < max && (
        <label className="flex size-11 cursor-pointer items-center justify-center rounded-[10px] border border-dashed border-border-strong text-muted hover:border-primary hover:text-primary" title="Add color">
          <Plus className="size-4" />
          <input type="color" className="sr-only" defaultValue="#0f766e" onChange={(e) => onChange([...value, e.target.value])} aria-label="Add brand color" />
        </label>
      )}
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)}
      className={cn("relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50", checked ? "bg-primary" : "bg-border-strong")}>
      <span className={cn("inline-block size-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
    </button>
  );
}

export function Slider({ value, onChange, min = 0, max = 100, step = 1, className, label }: { value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; className?: string; label?: string }) {
  return (
    <input type="range" aria-label={label} min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
      className={cn("h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border accent-[var(--primary)]", className)} />
  );
}
