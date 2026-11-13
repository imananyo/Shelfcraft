"use client";
import {
  AlignCenterHorizontal, AlignCenterVertical, AlignEndHorizontal, AlignEndVertical, AlignStartHorizontal, AlignStartVertical,
  ArrowDown, ArrowUp, BringToFront, Circle, Copy, Eye, EyeOff, Group as GroupIcon, Image as ImageIcon, LayoutTemplate, Lock, Minus,
  MousePointer2, SendToBack, Square, Trash2, Type, Ungroup, Unlock,
} from "lucide-react";
import * as React from "react";
import { AssetPicker } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Select, Slider } from "@/components/ui/form";
import { Tip } from "@/components/ui/overlay";
import { FONT_CHOICES, ensureFont, useEditor } from "@/lib/editor-store";
import type { Asset, DocLayer } from "@/lib/types";
import { cn } from "@/lib/utils";

const LAYER_ICON: Record<string, React.ReactNode> = {
  text: <Type className="size-3.5" />, rect: <Square className="size-3.5" />, ellipse: <Circle className="size-3.5" />,
  image: <ImageIcon className="size-3.5" />, line: <Minus className="size-3.5" />, group: <GroupIcon className="size-3.5" />,
};

export function ToolRail({ onTemplates }: { onTemplates: () => void }) {
  const { addLayer, doc } = useEditor();
  const [picker, setPicker] = React.useState(false);
  if (!doc) return null;
  const s = Math.min(doc.width, doc.height);
  const tools = [
    { label: "Select (V)", icon: <MousePointer2 />, onClick: () => useEditor.getState().select([]) },
    { label: "Text (T)", icon: <Type />, onClick: () => addLayer({ type: "text", name: "Text", text: "Your text", fontFamily: "Inter", fontSize: Math.round(s / 14), fill: "#1c1917", align: "left", lineHeight: 1.2, width: Math.round(doc.width * 0.6), height: Math.round(s / 10) }) },
    { label: "Rectangle (R)", icon: <Square />, onClick: () => addLayer({ type: "rect", name: "Rectangle", fill: "#0f766e", cornerRadius: Math.round(s / 60), width: Math.round(s * 0.35), height: Math.round(s * 0.22) }) },
    { label: "Ellipse (O)", icon: <Circle />, onClick: () => addLayer({ type: "ellipse", name: "Ellipse", fill: "#7c3aed", width: Math.round(s * 0.25), height: Math.round(s * 0.25) }) },
    { label: "Line (L)", icon: <Minus />, onClick: () => { const w = Math.round(doc.width * 0.4); addLayer({ type: "line", name: "Line", points: [0, 0, w, 0], stroke: "#1c1917", strokeWidth: Math.max(2, Math.round(s / 300)), width: w, height: 1, x: Math.round((doc.width - w) / 2), y: Math.round(doc.height / 2) }); } },
    { label: "Image", icon: <ImageIcon />, onClick: () => setPicker(true) },
    { label: "Templates", icon: <LayoutTemplate />, onClick: onTemplates },
  ];
  const addImage = (a: Asset) => {
    const maxW = doc.width * 0.6, maxH = doc.height * 0.6;
    const k = Math.min(maxW / (a.width ?? maxW), maxH / (a.height ?? maxH), 1.5);
    addLayer({ type: "image", name: a.title.slice(0, 40), assetId: a.id, fit: "fill", width: Math.round((a.width ?? maxW) * k), height: Math.round((a.height ?? maxH) * k) });
  };
  return (
    <div className="flex w-[52px] shrink-0 flex-col items-center gap-1 border-r border-border bg-surface py-2">
      {tools.map((t) => (
        <Tip key={t.label} content={t.label} side="right">
          <button onClick={t.onClick} aria-label={t.label} className="flex size-9 items-center justify-center rounded-[9px] text-foreground/75 hover:bg-sunken hover:text-foreground [&_svg]:size-[18px]">{t.icon}</button>
        </Tip>
      ))}
      <AssetPicker open={picker} onOpenChange={setPicker} onPick={addImage} title="Add an image layer" />
    </div>
  );
}

export function LayersPanel() {
  const { doc, selected, select, updateLayers, moveTo } = useEditor();
  const [renaming, setRenaming] = React.useState<string | null>(null);
  const [dragId, setDragId] = React.useState<string | null>(null);
  if (!doc) return null;
  // Show top-most first; group children nested under their group.
  const top = [...doc.layers].reverse().filter((l) => !l.parentId);
  const children = (gid: string) => [...doc.layers].reverse().filter((l) => l.parentId === gid);
  const row = (l: DocLayer, depth = 0) => (
    <div key={l.id}>
      <div draggable onDragStart={() => setDragId(l.id)} onDragOver={(e) => e.preventDefault()}
        onDrop={() => { if (dragId && dragId !== l.id) moveTo(dragId, doc.layers.findIndex((x) => x.id === l.id)); setDragId(null); }}
        onClick={(e) => select([l.id], e.shiftKey)}
        className={cn("group flex h-8 cursor-pointer items-center gap-2 rounded-[8px] px-2 text-[12.5px]", selected.includes(l.id) ? "bg-ai-soft text-foreground" : "hover:bg-sunken", !l.visible && "opacity-50")}
        style={{ paddingLeft: 8 + depth * 14 }}>
        <span className="text-muted">{LAYER_ICON[l.type]}</span>
        {renaming === l.id ? (
          <input autoFocus defaultValue={l.name} className="h-6 min-w-0 flex-1 rounded border border-primary bg-surface px-1 text-[12.5px] outline-none"
            onBlur={(e) => { updateLayers([l.id], { name: e.target.value.slice(0, 120) || l.name }); setRenaming(null); }}
            onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); e.stopPropagation(); }} />
        ) : <span className="min-w-0 flex-1 truncate" onDoubleClick={() => setRenaming(l.id)}>{l.type === "text" && l.text ? l.text.slice(0, 40) : l.name}</span>}
        <button aria-label={l.locked ? "Unlock layer" : "Lock layer"} onClick={(e) => { e.stopPropagation(); updateLayers([l.id], { locked: !l.locked }); }}
          className={cn("text-muted hover:text-foreground", !l.locked && "opacity-0 group-hover:opacity-100")}>{l.locked ? <Lock className="size-3.5" /> : <Unlock className="size-3.5" />}</button>
        <button aria-label={l.visible ? "Hide layer" : "Show layer"} onClick={(e) => { e.stopPropagation(); updateLayers([l.id], { visible: !l.visible }); }}
          className={cn("text-muted hover:text-foreground", l.visible && "opacity-0 group-hover:opacity-100")}>{l.visible ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}</button>
      </div>
      {l.type === "group" && children(l.id).map((c) => row(c, depth + 1))}
    </div>
  );
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-3 pb-1 pt-3"><span className="text-[11px] font-medium uppercase tracking-wider text-muted">Layers</span><span className="text-[11px] text-muted">{doc.layers.filter((l) => l.type !== "group").length}</span></div>
      <div className="scrollbar-thin flex-1 overflow-y-auto px-1.5 pb-3">
        {top.length === 0 ? <div className="px-2 py-6 text-center text-xs text-muted">Add text, shapes or images from the left toolbar.</div> : top.map((l) => row(l))}
      </div>
      <div className="border-t border-border px-3 py-2 text-[11px] text-muted">Drag to reorder · double-click to rename</div>
    </div>
  );
}

function Num({ label, value, onChange, step = 1, min, max }: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number }) {
  return (
    <label className="flex items-center gap-1.5 rounded-[8px] border border-border-strong bg-surface px-2 focus-within:border-primary">
      <span className="w-3 text-[11px] text-muted">{label}</span>
      <input type="number" step={step} min={min} max={max} value={Number.isFinite(value) ? Math.round(value * 100) / 100 : 0}
        onChange={(e) => e.target.value !== "" && onChange(Number(e.target.value))} className="h-7 w-full min-w-0 bg-transparent text-[12.5px] tabular-nums outline-none" />
    </label>
  );
}

function Swatch({ value, onChange, label }: { value?: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="flex items-center gap-2 rounded-[8px] border border-border-strong bg-surface px-2 py-1 text-[12px]">
      <span className="size-5 rounded border border-border" style={{ background: value || "transparent" }} />
      <input type="color" value={value && value.startsWith("#") && value.length === 7 ? value : "#000000"} onChange={(e) => onChange(e.target.value)} className="sr-only" aria-label={label} />
      <span className="font-mono text-[11px] text-muted">{value || "none"}</span>
    </label>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="flex flex-col gap-2 border-b border-border px-3 py-3"><div className="text-[11px] font-medium uppercase tracking-wider text-muted">{title}</div>{children}</div>;
}

export function PropertiesPanel({ brandColors }: { brandColors: string[] }) {
  const st = useEditor();
  const { doc, selected, updateLayers, commit } = st;
  const [replacePicker, setReplacePicker] = React.useState(false);
  const [bgPicker, setBgPicker] = React.useState(false);
  if (!doc) return null;
  const layers = doc.layers.filter((l) => selected.includes(l.id) && l.type !== "group");
  const one = layers.length === 1 ? layers[0] : null;
  const ids = layers.map((l) => l.id);
  const up = (p: Partial<DocLayer>, merge = true) => updateLayers(ids, p, merge);
  const palette = [...new Set([...brandColors, "#ffffff", "#1c1917", "#f6f4f1", "#0f766e", "#7c3aed", "#e11d48", "#f59e0b"])].slice(0, 12);

  if (!layers.length) {
    return (
      <div className="flex flex-col">
        <Section title="Canvas">
          <div className="grid grid-cols-2 gap-2">
            <Num label="W" value={doc.width} min={16} max={8000} onChange={(v) => commit((d) => { d.width = Math.max(16, Math.min(8000, Math.round(v))); }, { merge: true })} />
            <Num label="H" value={doc.height} min={16} max={8000} onChange={(v) => commit((d) => { d.height = Math.max(16, Math.min(8000, Math.round(v))); }, { merge: true })} />
          </div>
          <Select className="h-8 text-[12.5px]" value="" onChange={(e) => { const [w, h] = e.target.value.split("x").map(Number); if (w) commit((d) => { d.width = w; d.height = h; }); }} aria-label="Canvas size preset">
            <option value="">Size presets…</option>
            {[["2000x2000", "Listing image 2000²"], ["1080x1080", "Square post"], ["1080x1350", "Portrait 4:5"], ["1080x1920", "Story 9:16"], ["1920x1080", "Landscape 16:9"], ["1200x628", "Sponsored Brand"], ["970x600", "A+ Basic banner"], ["1464x600", "A+ Premium banner"], ["600x450", "A+ mobile"]].map(([v, l]) => <option key={v} value={v}>{l} · {v}</option>)}
          </Select>
        </Section>
        <Section title="Background">
          <Swatch label="Background color" value={doc.background} onChange={(v) => commit((d) => { d.background = v; }, { merge: true })} />
          <div className="flex flex-wrap gap-1.5">{palette.map((c) => <button key={c} aria-label={`Background ${c}`} onClick={() => commit((d) => { d.background = c; })} className="size-6 rounded-full border border-border" style={{ background: c }} />)}</div>
          <Button size="sm" variant="outline" onClick={() => setBgPicker(true)}><ImageIcon />Background image</Button>
          <p className="text-[11px] text-muted">Adds a locked, full-canvas image at the bottom. Replace it any time.</p>
        </Section>
        <div className="px-3 py-4 text-xs text-muted">Select a layer to edit it. Shortcuts: Ctrl+Z/Y undo/redo · Ctrl+D duplicate · Del delete · Ctrl+G group · arrows nudge (Shift ×10) · Space+drag pan · Ctrl+wheel zoom.</div>
        <AssetPicker open={bgPicker} onOpenChange={setBgPicker} title="Background image" onPick={(a) => commit((d) => {
          const existing = d.layers.find((l) => l.name === "Background image" && l.type === "image");
          if (existing) { existing.assetId = a.id; return; }
          d.layers.unshift({ id: crypto.randomUUID().replace(/-/g, "").slice(0, 12), type: "image", name: "Background image", x: 0, y: 0, width: d.width, height: d.height, rotation: 0, opacity: 1, locked: true, visible: true, assetId: a.id, fit: "cover" });
        })} />
      </div>
    );
  }

  const first = layers[0];
  return (
    <div className="flex flex-col">
      <Section title={one ? `${one.type} layer` : `${layers.length} layers`}>
        <div className="grid grid-cols-2 gap-2">
          <Num label="X" value={first.x} onChange={(v) => up({ x: Math.round(v) })} />
          <Num label="Y" value={first.y} onChange={(v) => up({ y: Math.round(v) })} />
          {one && one.type !== "line" && <><Num label="W" value={one.width} min={1} onChange={(v) => up({ width: Math.max(1, Math.round(v)) })} /><Num label="H" value={one.height} min={1} onChange={(v) => up({ height: Math.max(1, Math.round(v)) })} /></>}
          <Num label="°" value={first.rotation} onChange={(v) => up({ rotation: v })} />
        </div>
        <div className="flex items-center gap-2 text-[12px]"><span className="w-14 text-muted">Opacity</span><Slider value={Math.round(first.opacity * 100)} min={0} max={100} onChange={(v) => up({ opacity: v / 100 })} label="Opacity" /><span className="w-9 text-right tabular-nums text-muted">{Math.round(first.opacity * 100)}%</span></div>
        <div className="flex flex-wrap gap-1">
          {([["left", AlignStartVertical], ["center", AlignCenterVertical], ["right", AlignEndVertical], ["top", AlignStartHorizontal], ["middle", AlignCenterHorizontal], ["bottom", AlignEndHorizontal]] as const).map(([k, I]) => (
            <Tip key={k} content={`Align ${k}${layers.length === 1 ? " (to canvas)" : ""}`}><button onClick={() => st.align(k)} aria-label={`Align ${k}`} className="flex size-7 items-center justify-center rounded-[7px] border border-border hover:bg-sunken"><I className="size-3.5" /></button></Tip>
          ))}
        </div>
      </Section>

      {one?.type === "text" && (
        <Section title="Text">
          <textarea value={one.text ?? ""} onChange={(e) => up({ text: e.target.value })} rows={3} aria-label="Text content" className="rounded-[8px] border border-border-strong bg-surface px-2 py-1.5 text-[12.5px] outline-none focus:border-primary" />
          <Select className="h-8 text-[12.5px]" value={one.fontFamily ?? "Inter"} onChange={(e) => { ensureFont(e.target.value); up({ fontFamily: e.target.value }, false); }} aria-label="Font">
            {[...new Set([one.fontFamily ?? "Inter", ...FONT_CHOICES])].map((f) => <option key={f}>{f}</option>)}
          </Select>
          <div className="grid grid-cols-2 gap-2">
            <Num label="Sz" value={one.fontSize ?? 32} min={4} onChange={(v) => up({ fontSize: Math.max(4, v) })} />
            <Num label="↕" value={one.lineHeight ?? 1.2} step={0.05} onChange={(v) => up({ lineHeight: v })} />
            <Num label="↔" value={one.letterSpacing ?? 0} step={0.5} onChange={(v) => up({ letterSpacing: v })} />
            <Select className="h-[30px] text-[12px]" value={one.fontStyle ?? "normal"} onChange={(e) => up({ fontStyle: e.target.value }, false)} aria-label="Font style">
              <option value="normal">Regular</option><option value="bold">Bold</option><option value="italic">Italic</option><option value="bold italic">Bold italic</option>
            </Select>
          </div>
          <div className="flex gap-1">{(["left", "center", "right"] as const).map((a) => <button key={a} onClick={() => up({ align: a }, false)} className={cn("h-7 flex-1 rounded-[7px] border border-border text-[11.5px] capitalize", one.align === a && "border-primary bg-primary-soft text-primary")}>{a}</button>)}</div>
          <Swatch label="Text color" value={one.fill} onChange={(v) => up({ fill: v })} />
        </Section>
      )}

      {layers.some((l) => l.type === "rect" || l.type === "ellipse" || l.type === "line") && (
        <Section title="Appearance">
          {first.type !== "line" && <><div className="text-[11px] text-muted">Fill</div><Swatch label="Fill color" value={first.fill} onChange={(v) => up({ fill: v })} /></>}
          <div className="text-[11px] text-muted">Stroke</div>
          <div className="grid grid-cols-[1fr_80px] gap-2"><Swatch label="Stroke color" value={first.stroke} onChange={(v) => up({ stroke: v })} /><Num label="W" value={first.strokeWidth ?? 0} min={0} onChange={(v) => up({ strokeWidth: Math.max(0, v) })} /></div>
          {first.type === "rect" && <Num label="R" value={first.cornerRadius ?? 0} min={0} onChange={(v) => up({ cornerRadius: Math.max(0, v) })} />}
        </Section>
      )}

      {(one?.type === "text" || layers.some((l) => l.type === "rect" || l.type === "ellipse")) && (
        <Section title="Brand palette">
          <div className="flex flex-wrap gap-1.5">{palette.map((c) => <button key={c} aria-label={`Use ${c}`} onClick={() => up({ fill: c }, false)} className="size-6 rounded-full border border-border" style={{ background: c }} />)}</div>
        </Section>
      )}

      {one?.type === "image" && (
        <Section title="Image">
          <Select className="h-8 text-[12.5px]" value={one.fit ?? "fill"} onChange={(e) => up({ fit: e.target.value as DocLayer["fit"] }, false)} aria-label="Fit">
            <option value="fill">Stretch to box</option><option value="contain">Fit inside</option><option value="cover">Fill & crop</option>
          </Select>
          <CropControls layer={one} onChange={(crop) => up({ crop }, true)} />
          <Button size="sm" variant="outline" onClick={() => setReplacePicker(true)}>Replace image</Button>
          {one.assetId && <a href={`/edit?asset=${one.assetId}`} className="text-[12px] font-medium text-primary hover:underline">Spot edit this image →</a>}
          <AssetPicker open={replacePicker} onOpenChange={setReplacePicker} onPick={(a) => up({ assetId: a.id, crop: null }, false)} />
        </Section>
      )}

      <Section title="Arrange">
        <div className="grid grid-cols-4 gap-1">
          <Tip content="Bring to front"><Button size="icon-sm" variant="outline" aria-label="Bring to front" onClick={() => ids.forEach((id) => st.reorder(id, "top"))}><BringToFront /></Button></Tip>
          <Tip content="Forward"><Button size="icon-sm" variant="outline" aria-label="Bring forward" onClick={() => ids.forEach((id) => st.reorder(id, "up"))}><ArrowUp /></Button></Tip>
          <Tip content="Backward"><Button size="icon-sm" variant="outline" aria-label="Send backward" onClick={() => ids.forEach((id) => st.reorder(id, "down"))}><ArrowDown /></Button></Tip>
          <Tip content="Send to back"><Button size="icon-sm" variant="outline" aria-label="Send to back" onClick={() => ids.forEach((id) => st.reorder(id, "bottom"))}><SendToBack /></Button></Tip>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <Button size="sm" variant="outline" onClick={st.duplicateSelected}><Copy />Duplicate</Button>
          <Button size="sm" variant="outline" onClick={() => updateLayers(ids, { locked: !first.locked }, false)}>{first.locked ? <Unlock /> : <Lock />}{first.locked ? "Unlock" : "Lock"}</Button>
          {selected.some((id) => doc.layers.find((l) => l.id === id)?.type === "group")
            ? <Button size="sm" variant="outline" onClick={st.ungroup}><Ungroup />Ungroup</Button>
            : <Button size="sm" variant="outline" disabled={layers.length < 2} onClick={st.group}><GroupIcon />Group</Button>}
          <Button size="sm" variant="outline" className="text-danger" onClick={st.removeSelected}><Trash2 />Delete</Button>
        </div>
      </Section>
    </div>
  );
}

/** Crop as percentages of the source image (stored in source pixels). */
function CropControls({ layer, onChange }: { layer: DocLayer; onChange: (c: DocLayer["crop"]) => void }) {
  const [natural, setNatural] = React.useState<{ w: number; h: number } | null>(null);
  React.useEffect(() => {
    if (!layer.assetId) return;
    const i = new window.Image();
    i.onload = () => setNatural({ w: i.naturalWidth, h: i.naturalHeight });
    i.src = `/api/assets/${layer.assetId}/file`;
  }, [layer.assetId]);
  if (!natural) return null;
  const c = layer.crop ?? { x: 0, y: 0, width: natural.w, height: natural.h };
  const pct = { l: (c.x / natural.w) * 100, t: (c.y / natural.h) * 100, r: 100 - ((c.x + c.width) / natural.w) * 100, b: 100 - ((c.y + c.height) / natural.h) * 100 };
  const set = (k: "l" | "t" | "r" | "b", v: number) => {
    const p = { ...pct, [k]: v };
    if (p.l + p.r > 95 || p.t + p.b > 95) return;
    onChange({ x: (p.l / 100) * natural.w, y: (p.t / 100) * natural.h, width: ((100 - p.l - p.r) / 100) * natural.w, height: ((100 - p.t - p.b) / 100) * natural.h });
  };
  return (
    <div className="flex flex-col gap-1.5 rounded-[8px] bg-sunken p-2">
      <div className="flex items-center justify-between text-[11px] text-muted">Crop<button className="text-primary hover:underline" onClick={() => onChange(null)}>Reset</button></div>
      {(["l", "t", "r", "b"] as const).map((k) => (
        <div key={k} className="flex items-center gap-2 text-[11px]"><span className="w-10 text-muted">{{ l: "Left", t: "Top", r: "Right", b: "Bottom" }[k]}</span>
          <Slider value={Math.round(pct[k])} min={0} max={90} onChange={(v) => set(k, v)} label={`Crop ${k}`} /><span className="w-8 text-right tabular-nums">{Math.round(pct[k])}%</span></div>
      ))}
    </div>
  );
}

export function useEditorShortcuts(enabled: boolean) {
  React.useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable=true]")) return;
      const s = useEditor.getState();
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); if (e.shiftKey) s.redo(); else s.undo(); }
      else if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); s.redo(); }
      else if (mod && e.key.toLowerCase() === "d") { e.preventDefault(); s.duplicateSelected(); }
      else if (mod && e.key.toLowerCase() === "g") { e.preventDefault(); if (e.shiftKey) s.ungroup(); else s.group(); }
      else if (mod && e.key.toLowerCase() === "a") { e.preventDefault(); s.select(s.doc?.layers.filter((l) => !l.locked && l.type !== "group").map((l) => l.id) ?? []); }
      else if (e.key === "Delete" || e.key === "Backspace") { if (s.selected.length) { e.preventDefault(); s.removeSelected(); } }
      else if (e.key === "Escape") s.select([]);
      else if (e.key.startsWith("Arrow") && s.selected.length) {
        e.preventDefault();
        const d = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0, dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
        s.updateLayers(s.selected, (l) => (l.locked ? {} : { x: l.x + dx, y: l.y + dy }), true);
      } else if (!mod && e.key.toLowerCase() === "+" ) s.setZoom(s.zoom * 1.15);
      else if (!mod && e.key === "-") s.setZoom(s.zoom / 1.15);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
