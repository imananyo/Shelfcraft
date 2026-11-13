"use client";
import type Konva from "konva";
import * as React from "react";
import { Ellipse, Group, Image as KImage, Layer, Line, Rect, Stage, Text, Transformer } from "react-konva";
import { ensureFont, useEditor } from "@/lib/editor-store";
import type { DocLayer } from "@/lib/types";

/** Shared handle so toolbar export can rasterize the document at native resolution. */
export const stageHandle: { exportDataURL: ((mime: string, quality?: number) => string | null) | null } = { exportDataURL: null };

const SNAP = 8; // px in document space

function useHtmlImage(assetId?: string | null) {
  const [img, setImg] = React.useState<HTMLImageElement | null>(null);
  React.useEffect(() => {
    if (!assetId) { setImg(null); return; }
    const i = new window.Image();
    i.src = `/api/assets/${assetId}/file`;
    i.onload = () => setImg(i);
    i.onerror = () => setImg(null);
    return () => { i.onload = null; };
  }, [assetId]);
  return img;
}

function ImageNode({ layer, common }: { layer: DocLayer; common: Record<string, unknown> }) {
  const img = useHtmlImage(layer.assetId);
  if (!img) {
    return <Rect {...common} width={layer.width} height={layer.height} fill="#d6d3d1" opacity={0.5} dash={[12, 8]} stroke="#a8a29e" strokeWidth={2} />;
  }
  // fit: contain/cover/fill with optional crop (crop in source pixels).
  let crop = layer.crop ?? undefined;
  let dx = 0, dy = 0, dw = layer.width, dh = layer.height;
  const sw = crop?.width ?? img.naturalWidth, sh = crop?.height ?? img.naturalHeight;
  if (layer.fit === "contain") {
    const s = Math.min(layer.width / sw, layer.height / sh);
    dw = sw * s; dh = sh * s; dx = (layer.width - dw) / 2; dy = (layer.height - dh) / 2;
  } else if (layer.fit === "cover" && !crop) {
    const s = Math.max(layer.width / sw, layer.height / sh);
    const cw = layer.width / s, ch = layer.height / s;
    crop = { x: (img.naturalWidth - cw) / 2, y: (img.naturalHeight - ch) / 2, width: cw, height: ch };
  }
  return (
    <Group {...common} width={layer.width} height={layer.height} clipX={0} clipY={0} clipWidth={layer.width} clipHeight={layer.height}>
      <Rect width={layer.width} height={layer.height} fill="transparent" />
      <KImage image={img} x={dx} y={dy} width={dw} height={dh} crop={crop} />
    </Group>
  );
}

export function EditorCanvas() {
  const { doc, selected, zoom, showGrid, snap, select, commit, setZoom } = useEditor();
  const wrap = React.useRef<HTMLDivElement>(null);
  const stageRef = React.useRef<Konva.Stage>(null);
  const trRef = React.useRef<Konva.Transformer>(null);
  const [size, setSize] = React.useState({ w: 800, h: 600 });
  const [pan, setPan] = React.useState({ x: 0, y: 0 });
  const [guides, setGuides] = React.useState<{ v: number[]; h: number[] }>({ v: [], h: [] });
  const [marquee, setMarquee] = React.useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [editing, setEditing] = React.useState<string | null>(null);
  const [fontsVersion, forceFontRedraw] = React.useState(0);
  const spaceDown = React.useRef(false);
  const [panMode, setPanMode] = React.useState(false); // render-visible mirror of spaceDown
  const dragStart = React.useRef<Record<string, { x: number; y: number }>>({});

  // Fit to container on load / resize.
  React.useEffect(() => {
    const el = wrap.current!;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const fitted = React.useRef(false);
  React.useEffect(() => {
    if (!doc || fitted.current || size.w < 50) return;
    fitted.current = true;
    setZoom(Math.min((size.w - 80) / doc.width, (size.h - 80) / doc.height));
  }, [doc, size, setZoom]);

  // Load fonts used by text layers, then redraw.
  const families = doc ? [...new Set(doc.layers.filter((l) => l.type === "text").map((l) => l.fontFamily ?? "Inter"))].join("|") : "";
  React.useEffect(() => {
    if (!families) return;
    Promise.all(families.split("|").map(ensureFont)).then(() => { forceFontRedraw((n) => n + 1); stageRef.current?.batchDraw(); });
  }, [families]);

  const ox = Math.round((size.w - (doc?.width ?? 0) * zoom) / 2 + pan.x);
  const oy = Math.round((size.h - (doc?.height ?? 0) * zoom) / 2 + pan.y);

  // Attach transformer to selected, unlocked, visible nodes.
  React.useEffect(() => {
    const tr = trRef.current, stage = stageRef.current;
    if (!tr || !stage || !doc) return;
    const nodes = selected
      .map((id) => doc.layers.find((l) => l.id === id))
      .filter((l): l is DocLayer => !!l && l.type !== "group" && !l.locked && l.visible && l.id !== editing)
      .map((l) => stage.findOne(`#${l.id}`))
      .filter(Boolean) as Konva.Node[];
    tr.nodes(nodes);
    tr.getLayer()?.batchDraw();
  }, [selected, doc, editing, fontsVersion]);

  // Export handle (renders only document area, without UI overlays).
  React.useEffect(() => {
    stageHandle.exportDataURL = (mime, quality) => {
      const stage = stageRef.current;
      if (!stage || !doc) return null;
      const tr = trRef.current;
      const ui = stage.find(".ui");
      const prevNodes = tr?.nodes() ?? [];
      tr?.nodes([]);
      ui.forEach((n) => n.hide());
      const url = stage.toDataURL({ x: ox, y: oy, width: doc.width * zoom, height: doc.height * zoom, pixelRatio: 1 / zoom, mimeType: mime, quality });
      ui.forEach((n) => n.show());
      tr?.nodes(prevNodes);
      return url;
    };
    return () => { stageHandle.exportDataURL = null; };
  }, [doc, ox, oy, zoom]);

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.code === "Space" && !(e.target as HTMLElement).closest("input,textarea")) { spaceDown.current = true; setPanMode(true); } };
    const up = (e: KeyboardEvent) => { if (e.code === "Space") { spaceDown.current = false; setPanMode(false); } };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, []);

  if (!doc) return <div ref={wrap} className="size-full" />;

  const toDoc = (p: { x: number; y: number }) => ({ x: (p.x - ox) / zoom, y: (p.y - oy) / zoom });

  const snapPos = (id: string, x: number, y: number, w: number, h: number) => {
    if (!snap) return { x, y, v: [], h: [] as number[] };
    const vs = [0, doc.width / 2, doc.width], hs = [0, doc.height / 2, doc.height];
    doc.layers.forEach((l) => {
      if (selected.includes(l.id) || l.id === id || !l.visible || l.type === "group") return;
      vs.push(l.x, l.x + l.width / 2, l.x + l.width);
      hs.push(l.y, l.y + l.height / 2, l.y + l.height);
    });
    let nx = x, ny = y;
    const gv: number[] = [], gh: number[] = [];
    for (const edge of [0, w / 2, w]) {
      const t = vs.find((v) => Math.abs(v - (x + edge)) < SNAP / zoom * 0.5 + 2);
      if (t !== undefined) { nx = t - edge; gv.push(t); break; }
    }
    for (const edge of [0, h / 2, h]) {
      const t = hs.find((v) => Math.abs(v - (y + edge)) < SNAP / zoom * 0.5 + 2);
      if (t !== undefined) { ny = t - edge; gh.push(t); break; }
    }
    return { x: nx, y: ny, v: gv, h: gh };
  };

  const onDragStart = (layer: DocLayer) => {
    if (!selected.includes(layer.id)) select([layer.id]);
    const ids = selected.includes(layer.id) ? selected : [layer.id];
    dragStart.current = Object.fromEntries(doc.layers.filter((l) => ids.includes(l.id)).map((l) => [l.id, { x: l.x, y: l.y }]));
  };
  const onDragMove = (layer: DocLayer, node: Konva.Node) => {
    const isEllipse = layer.type === "ellipse";
    const rawX = node.x() - (isEllipse ? layer.width / 2 : 0), rawY = node.y() - (isEllipse ? layer.height / 2 : 0);
    const s = snapPos(layer.id, rawX, rawY, layer.width, layer.height);
    node.position({ x: s.x + (isEllipse ? layer.width / 2 : 0), y: s.y + (isEllipse ? layer.height / 2 : 0) });
    setGuides({ v: s.v, h: s.h });
    // Move the other selected nodes along.
    const start = dragStart.current[layer.id];
    if (!start) return;
    const dx = s.x - start.x, dy = s.y - start.y;
    Object.entries(dragStart.current).forEach(([id, p]) => {
      if (id === layer.id) return;
      const other = doc.layers.find((l) => l.id === id);
      const n = stageRef.current?.findOne(`#${id}`);
      if (!other || !n) return;
      const off = other.type === "ellipse" ? { x: other.width / 2, y: other.height / 2 } : { x: 0, y: 0 };
      n.position({ x: p.x + dx + off.x, y: p.y + dy + off.y });
    });
  };
  const onDragEnd = (layer: DocLayer, node: Konva.Node) => {
    setGuides({ v: [], h: [] });
    const start = dragStart.current[layer.id];
    const isEllipse = layer.type === "ellipse";
    const nx = node.x() - (isEllipse ? layer.width / 2 : 0), ny = node.y() - (isEllipse ? layer.height / 2 : 0);
    if (!start) return;
    const dx = Math.round(nx - start.x), dy = Math.round(ny - start.y);
    const moved = Object.keys(dragStart.current);
    commit((d) => {
      d.layers = d.layers.map((l) => {
        if (moved.includes(l.id) || (l.type === "group" && moved.some((m) => d.layers.find((x) => x.id === m)?.parentId === l.id))) {
          const p = l.type === "line" ? { x: l.x + dx, y: l.y + dy } : { x: Math.round((dragStart.current[l.id]?.x ?? l.x) + dx), y: Math.round((dragStart.current[l.id]?.y ?? l.y) + dy) };
          return { ...l, ...p };
        }
        return l;
      });
    });
    dragStart.current = {};
  };

  const onTransformEnd = () => {
    const tr = trRef.current!;
    const nodes = tr.nodes();
    commit((d) => {
      nodes.forEach((n) => {
        const l = d.layers.find((x) => x.id === n.id());
        if (!l) return;
        const sx = n.scaleX(), sy = n.scaleY();
        n.scale({ x: 1, y: 1 });
        const w = Math.max(4, l.width * sx), h = Math.max(4, l.height * sy);
        if (l.type === "text") {
          const corner = Math.abs(sx - sy) < 0.01 && sy !== 1;
          if (corner) l.fontSize = Math.max(6, Math.round((l.fontSize ?? 32) * sy));
          l.width = Math.round(w);
          l.height = Math.round(corner ? h : l.height);
        } else if (l.type === "line" && l.points) {
          l.points = l.points.map((v, i) => Math.round(v * (i % 2 === 0 ? sx : sy)));
          l.width = Math.round(w); l.height = Math.round(h);
        } else {
          l.width = Math.round(w); l.height = Math.round(h);
        }
        l.rotation = Math.round(n.rotation() * 10) / 10;
        if (l.type === "ellipse") { l.x = Math.round(n.x() - l.width / 2); l.y = Math.round(n.y() - l.height / 2); }
        else { l.x = Math.round(n.x()); l.y = Math.round(n.y()); }
      });
    });
  };

  const startTextEdit = (layer: DocLayer) => {
    if (layer.locked) return;
    setEditing(layer.id);
  };

  const editingLayer = editing ? doc.layers.find((l) => l.id === editing) : null;
  const gridStep = Math.max(20, Math.round(Math.min(doc.width, doc.height) / 20));

  return (
    <div ref={wrap} className="relative size-full overflow-hidden bg-sunken" onWheel={(e) => {
      if (e.ctrlKey || e.metaKey) { e.preventDefault(); setZoom(zoom * (e.deltaY < 0 ? 1.1 : 0.9)); }
      else setPan((p) => ({ x: p.x - e.deltaX, y: p.y - e.deltaY }));
    }}>
      <Stage ref={stageRef} width={size.w} height={size.h}
        onMouseDown={(e) => {
          if (spaceDown.current || e.evt.button === 1) return;
          if (e.target === e.target.getStage() || e.target.name() === "doc-bg") {
            const p = toDoc(e.target.getStage()!.getPointerPosition()!);
            setMarquee({ x: p.x, y: p.y, w: 0, h: 0 });
            if (!e.evt.shiftKey) select([]);
          }
        }}
        onMouseMove={(e) => {
          const stage = e.target.getStage()!;
          if (spaceDown.current && e.evt.buttons === 1) { setPan((p) => ({ x: p.x + e.evt.movementX, y: p.y + e.evt.movementY })); stage.container().style.cursor = "grabbing"; return; }
          if (e.evt.buttons === 4) { setPan((p) => ({ x: p.x + e.evt.movementX, y: p.y + e.evt.movementY })); return; }
          if (!marquee) return;
          const p = toDoc(stage.getPointerPosition()!);
          setMarquee((m) => m && { ...m, w: p.x - m.x, h: p.y - m.y });
        }}
        onMouseUp={(e) => {
          e.target.getStage()!.container().style.cursor = "";
          if (!marquee) return;
          const x1 = Math.min(marquee.x, marquee.x + marquee.w), x2 = Math.max(marquee.x, marquee.x + marquee.w);
          const y1 = Math.min(marquee.y, marquee.y + marquee.h), y2 = Math.max(marquee.y, marquee.y + marquee.h);
          if (x2 - x1 > 4 || y2 - y1 > 4) {
            const hits = doc.layers.filter((l) => l.visible && !l.locked && l.type !== "group" && l.x < x2 && l.x + l.width > x1 && l.y < y2 && l.y + l.height > y1).map((l) => l.id);
            select(hits, e.evt.shiftKey);
          }
          setMarquee(null);
        }}>
        <Layer x={ox} y={oy} scaleX={zoom} scaleY={zoom}>
          <Rect name="doc-bg" width={doc.width} height={doc.height} fill={doc.background || "#ffffff"} shadowColor="black" shadowOpacity={0.12} shadowBlur={24} shadowOffsetY={4} />
          <Group clipX={0} clipY={0} clipWidth={doc.width} clipHeight={doc.height}>
            {doc.layers.map((l) => {
              if (!l.visible || l.type === "group") return null;
              const common = {
                id: l.id, x: l.x, y: l.y, rotation: l.rotation, opacity: l.opacity, draggable: !l.locked && !panMode,
                listening: !l.locked || selected.includes(l.id),
                onMouseDown: (e: Konva.KonvaEventObject<MouseEvent>) => { if (spaceDown.current) return; e.cancelBubble = true; if (!selected.includes(l.id) || e.evt.shiftKey) select([l.id], e.evt.shiftKey); },
                onTap: () => select([l.id]),
                onDragStart: () => onDragStart(l), onDragMove: (e: Konva.KonvaEventObject<DragEvent>) => onDragMove(l, e.target), onDragEnd: (e: Konva.KonvaEventObject<DragEvent>) => onDragEnd(l, e.target),
                onTransformEnd,
              };
              if (l.type === "text") return <Text key={`${l.id}-f${fontsVersion}`} {...common} width={l.width} text={l.text ?? ""} fontFamily={l.fontFamily ?? "Inter"} fontSize={l.fontSize ?? 32}
                fontStyle={l.fontStyle ?? "normal"} fill={l.fill ?? "#111"} align={l.align ?? "left"} lineHeight={l.lineHeight ?? 1.2} letterSpacing={l.letterSpacing ?? 0}
                opacity={editing === l.id ? 0 : l.opacity} onDblClick={() => startTextEdit(l)} onDblTap={() => startTextEdit(l)} />;
              if (l.type === "rect") return <Rect key={l.id} {...common} width={l.width} height={l.height} fill={l.fill} stroke={l.stroke || undefined} strokeWidth={l.strokeWidth ?? 0} cornerRadius={l.cornerRadius ?? 0} />;
              if (l.type === "ellipse") return <Ellipse key={l.id} {...common} x={l.x + l.width / 2} y={l.y + l.height / 2} radiusX={l.width / 2} radiusY={l.height / 2} fill={l.fill} stroke={l.stroke || undefined} strokeWidth={l.strokeWidth ?? 0} />;
              if (l.type === "line") return <Line key={l.id} {...common} points={l.points ?? []} stroke={l.stroke ?? "#111"} strokeWidth={l.strokeWidth ?? 4} dash={l.dash} hitStrokeWidth={20} lineCap="round" />;
              if (l.type === "image") return <ImageNode key={l.id} layer={l} common={common} />;
              return null;
            })}
          </Group>
          {showGrid && (
            <Group name="ui" listening={false}>
              {Array.from({ length: Math.floor(doc.width / gridStep) }).map((_, i) => <Line key={`gv${i}`} points={[(i + 1) * gridStep, 0, (i + 1) * gridStep, doc.height]} stroke="#7c3aed" opacity={0.12} strokeWidth={1 / zoom} />)}
              {Array.from({ length: Math.floor(doc.height / gridStep) }).map((_, i) => <Line key={`gh${i}`} points={[0, (i + 1) * gridStep, doc.width, (i + 1) * gridStep]} stroke="#7c3aed" opacity={0.12} strokeWidth={1 / zoom} />)}
            </Group>
          )}
          <Group name="ui" listening={false}>
            {guides.v.map((x, i) => <Line key={`v${i}`} points={[x, -4000, x, 8000]} stroke="#e11d48" strokeWidth={1 / zoom} dash={[4 / zoom, 4 / zoom]} />)}
            {guides.h.map((y, i) => <Line key={`h${i}`} points={[-4000, y, 8000, y]} stroke="#e11d48" strokeWidth={1 / zoom} dash={[4 / zoom, 4 / zoom]} />)}
            {marquee && <Rect x={marquee.x} y={marquee.y} width={marquee.w} height={marquee.h} fill="rgba(124,58,237,0.08)" stroke="#7c3aed" strokeWidth={1 / zoom} />}
          </Group>
          <Transformer ref={trRef} name="ui" rotationSnaps={[0, 45, 90, 135, 180, 225, 270, 315]} rotationSnapTolerance={4}
            anchorSize={9} anchorCornerRadius={3} borderStroke="#7c3aed" anchorStroke="#7c3aed" keepRatio={false}
            boundBoxFunc={(oldB, newB) => (newB.width < 4 || newB.height < 4 ? oldB : newB)} />
        </Layer>
      </Stage>
      {editingLayer && (
        <textarea autoFocus defaultValue={editingLayer.text ?? ""} aria-label="Edit text"
          style={{
            position: "absolute", left: ox + editingLayer.x * zoom, top: oy + editingLayer.y * zoom, width: editingLayer.width * zoom,
            minHeight: (editingLayer.fontSize ?? 32) * (editingLayer.lineHeight ?? 1.2) * zoom + 8, fontFamily: editingLayer.fontFamily,
            fontSize: (editingLayer.fontSize ?? 32) * zoom, lineHeight: editingLayer.lineHeight ?? 1.2, color: editingLayer.fill,
            fontWeight: editingLayer.fontStyle?.includes("bold") ? 700 : 400, fontStyle: editingLayer.fontStyle?.includes("italic") ? "italic" : "normal",
            textAlign: (editingLayer.align as "left") ?? "left", transform: `rotate(${editingLayer.rotation}deg)`, transformOrigin: "top left",
            background: "rgba(255,255,255,0.85)", outline: "2px solid #7c3aed", border: 0, padding: 0, margin: 0, resize: "none", overflow: "hidden",
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape" || (e.key === "Enter" && (e.ctrlKey || e.metaKey))) (e.target as HTMLTextAreaElement).blur();
            e.stopPropagation();
          }}
          onBlur={(e) => {
            const text = e.target.value;
            commit((d) => { const l = d.layers.find((x) => x.id === editingLayer.id); if (l) l.text = text; });
            setEditing(null);
          }} />
      )}
    </div>
  );
}
