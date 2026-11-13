"use client";
import { X } from "lucide-react";
import { Dialog as D, DropdownMenu as DM, Popover as P, Tooltip as T } from "radix-ui";
import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

export function Dialog({ open, onOpenChange, title, description, children, footer, className, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: React.ReactNode; description?: React.ReactNode;
  children?: React.ReactNode; footer?: React.ReactNode; className?: string; wide?: boolean;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px] data-[state=open]:animate-in" />
        <D.Content className={cn("fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-[18px] border border-border bg-surface shadow-[var(--shadow-pop)] focus:outline-none",
          wide ? "max-w-3xl" : "max-w-lg", className)}>
          <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div>
              <D.Title className="text-base font-semibold">{title}</D.Title>
              {description ? <D.Description className="mt-0.5 text-[13px] text-muted">{description}</D.Description> : <D.Description className="sr-only">{String(title)}</D.Description>}
            </div>
            <D.Close asChild><Button variant="ghost" size="icon-sm" aria-label="Close"><X /></Button></D.Close>
          </div>
          <div className="scrollbar-thin overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

export function Confirm({ open, onOpenChange, title, body, confirmLabel = "Delete", onConfirm, destructive = true, loading }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; body?: React.ReactNode; confirmLabel?: string; onConfirm: () => void; destructive?: boolean; loading?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} description={body}
      footer={<>
        <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button variant={destructive ? "destructive" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
      </>} />
  );
}

export function Menu({ trigger, children, align = "end" }: { trigger: React.ReactNode; children: React.ReactNode; align?: "start" | "end" | "center" }) {
  return (
    <DM.Root>
      <DM.Trigger asChild>{trigger}</DM.Trigger>
      <DM.Portal>
        <DM.Content align={align} sideOffset={6} className="z-50 min-w-48 rounded-[12px] border border-border bg-surface p-1 shadow-[var(--shadow-pop)]">
          {children}
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}

export function MenuItem({ children, onSelect, destructive, disabled, icon }: { children: React.ReactNode; onSelect?: () => void; destructive?: boolean; disabled?: boolean; icon?: React.ReactNode }) {
  return (
    <DM.Item disabled={disabled} onSelect={onSelect}
      className={cn("flex cursor-pointer select-none items-center gap-2 rounded-[8px] px-2.5 py-1.5 text-[13px] outline-none data-[disabled]:opacity-50 data-[highlighted]:bg-sunken [&_svg]:size-4 [&_svg]:text-muted",
        destructive && "text-danger [&_svg]:text-danger")}>
      {icon}{children}
    </DM.Item>
  );
}
export const MenuSeparator = () => <DM.Separator className="my-1 h-px bg-border" />;
export const MenuLabel = ({ children }: { children: React.ReactNode }) => <DM.Label className="px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-muted">{children}</DM.Label>;

export function Popover({ trigger, children, className, align = "end" }: { trigger: React.ReactNode; children: React.ReactNode; className?: string; align?: "start" | "end" | "center" }) {
  return (
    <P.Root>
      <P.Trigger asChild>{trigger}</P.Trigger>
      <P.Portal>
        <P.Content align={align} sideOffset={8} className={cn("z-50 w-80 rounded-[14px] border border-border bg-surface shadow-[var(--shadow-pop)] focus:outline-none", className)}>
          {children}
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}

export function Tip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  if (!content) return <>{children}</>;
  return (
    <T.Root delayDuration={250}>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content side={side} sideOffset={6} className="z-[60] max-w-64 rounded-[8px] bg-foreground px-2.5 py-1.5 text-xs text-background shadow-[var(--shadow-pop)]">
          {content}
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}

export const TooltipProvider = T.Provider;
