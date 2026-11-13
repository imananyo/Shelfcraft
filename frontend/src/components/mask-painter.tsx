"use client";
import { Brush, Eraser, RotateCcw } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/form";
import { cn } from "@/lib/utils";

export interface MaskPainterHandle { toDataURL: () => string | null; clear: () => void; isEmpty: () => boolean }

/** Paint a mask over an image. Mask is exported at the image's natural resolution (white = edit area). */
export const MaskPainter = React.forwardRef<MaskPainterHandle, { src: string; enabled: boolean; className?: string }>(({ src, enabled, className }, ref) => {
  const imgRef = React.useRef<HTMLImageElement>(null);
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const [brush, setBrush] = React.useState(40);
  const [mode, setMode] = React.useState<"paint" | "erase">("paint");
  const [painted, setPainted] = React.useState(false);
  const drawing = React.useRef(false);
  const last = React.useRef<{ x: number; y: number } | null>(null);

  const sync = React.useCallback(() => {
    const img = imgRef.current, c = canvasRef.current;
    if (!img || !c || !img.naturalWidth) return;
    if (c.width !== img.naturalWidth) { c.width = img.naturalWidth; c.height = img.naturalHeight; setPainted(false); }
  }, []);

  React.useImperativeHandle(ref, () => ({
    toDataURL: () => (painted && canvasRef.current ? canvasRef.current.toDataURL("image/png") : null),
    clear: () => { const c = canvasRef.current; c?.getContext("2d")?.clearRect(0, 0, c.width, c.height); setPainted(false); },
    isEmpty: () => !painted,
  }), [painted]);

  const pos = (e: React.PointerEvent) => {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * c.width, y: ((e.clientY - r.top) / r.height) * c.height, scale: c.width / r.width };
  };
  const stroke = (e: React.PointerEvent) => {
    const c = canvasRef.current!;
    const ctx = c.getContext("2d")!;
    const p = pos(e);
    ctx.globalCompositeOperation = mode === "paint" ? "source-over" : "destination-out";
    ctx.strokeStyle = "rgba(124,58,237,0.55)";
    ctx.fillStyle = "rgba(124,58,237,0.55)";
    ctx.lineWidth = brush * p.scale;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    if (last.current) { ctx.moveTo(last.current.x, last.current.y); ctx.lineTo(p.x, p.y); ctx.stroke(); }
    else { ctx.arc(p.x, p.y, (brush * p.scale) / 2, 0, Math.PI * 2); ctx.fill(); }
    last.current = p;
    if (mode === "paint") setPainted(true);
  };

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {enabled && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-[10px] border border-border-strong p-0.5">
            <button onClick={() => setMode("paint")} className={cn("flex h-7 items-center gap-1.5 rounded-[8px] px-2.5 text-[12.5px]", mode === "paint" && "bg-ai-soft text-ai")}><Brush className="size-3.5" />Paint</button>
            <button onClick={() => setMode("erase")} className={cn("flex h-7 items-center gap-1.5 rounded-[8px] px-2.5 text-[12.5px]", mode === "erase" && "bg-sunken")}><Eraser className="size-3.5" />Erase</button>
          </div>
          <span className="text-xs text-muted">Brush</span><Slider className="w-32" min={6} max={160} value={brush} onChange={setBrush} label="Brush size" />
          <Button size="sm" variant="ghost" onClick={() => { const c = canvasRef.current; c?.getContext("2d")?.clearRect(0, 0, c.width, c.height); setPainted(false); }}><RotateCcw />Clear</Button>
        </div>
      )}
      <div className="checkerboard relative mx-auto w-fit max-w-full overflow-hidden rounded-[12px] border border-border">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img ref={imgRef} src={src} alt="Image to edit" onLoad={sync} className="block max-h-[62vh] max-w-full select-none" draggable={false} />
        <canvas ref={canvasRef} aria-label="Mask painting area"
          className={cn("absolute inset-0 size-full touch-none", enabled ? "cursor-crosshair" : "pointer-events-none opacity-0")}
          onPointerDown={(e) => { if (!enabled) return; drawing.current = true; last.current = null; (e.target as HTMLElement).setPointerCapture(e.pointerId); stroke(e); }}
          onPointerMove={(e) => drawing.current && stroke(e)}
          onPointerUp={() => { drawing.current = false; last.current = null; }} />
      </div>
    </div>
  );
});
MaskPainter.displayName = "MaskPainter";

/** Draggable before/after comparison. */
export function BeforeAfter({ before, after }: { before: string; after: string }) {
  const [pct, setPct] = React.useState(50);
  const box = React.useRef<HTMLDivElement>(null);
  const move = (clientX: number) => {
    const r = box.current!.getBoundingClientRect();
    setPct(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  };
  return (
    <div ref={box} className="checkerboard relative mx-auto w-fit max-w-full select-none overflow-hidden rounded-[12px] border border-border"
      onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture(e.pointerId); move(e.clientX); }}
      onPointerMove={(e) => e.buttons === 1 && move(e.clientX)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={after} alt="After" className="block max-h-[62vh] max-w-full" draggable={false} />
      <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 ${100 - pct}% 0 0)` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={before} alt="Before" className="block size-full object-fill" draggable={false} />
      </div>
      <div className="absolute inset-y-0 w-0.5 bg-white shadow-[0_0_0_1px_rgba(0,0,0,.2)]" style={{ left: `${pct}%` }}>
        <div className="absolute top-1/2 left-1/2 flex size-8 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full bg-white text-[10px] font-bold text-black shadow">⇆</div>
      </div>
      <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">Before</span>
      <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] text-white">After</span>
    </div>
  );
}
