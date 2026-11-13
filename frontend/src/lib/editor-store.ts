"use client";
import { create } from "zustand";
import type { DocLayer, EditorDoc } from "./types";
import { uid } from "./utils";

const HISTORY_LIMIT = 100;

interface EditorState {
  doc: EditorDoc | null;
  selected: string[];
  past: EditorDoc[];
  future: EditorDoc[];
  dirtyCounter: number; // increments on every committed change → triggers autosave
  zoom: number;
  showGrid: boolean;
  snap: boolean;
  cropping: string | null;
  load: (doc: EditorDoc | null) => void;
  commit: (fn: (doc: EditorDoc) => EditorDoc | void, opts?: { merge?: boolean }) => void;
  undo: () => void;
  redo: () => void;
  select: (ids: string[], additive?: boolean) => void;
  setZoom: (z: number) => void;
  toggleGrid: () => void;
  toggleSnap: () => void;
  setCropping: (id: string | null) => void;
  // layer helpers
  updateLayers: (ids: string[], patch: Partial<DocLayer> | ((l: DocLayer) => Partial<DocLayer>), merge?: boolean) => void;
  addLayer: (layer: Partial<DocLayer> & Pick<DocLayer, "type">) => string;
  removeSelected: () => void;
  duplicateSelected: () => void;
  reorder: (id: string, dir: "up" | "down" | "top" | "bottom") => void;
  moveTo: (id: string, index: number) => void;
  group: () => void;
  ungroup: () => void;
  align: (how: "left" | "center" | "right" | "top" | "middle" | "bottom") => void;
}

const clone = (d: EditorDoc): EditorDoc => structuredClone(d);
let lastMergeKey = 0;

export const useEditor = create<EditorState>((set, get) => ({
  doc: null, selected: [], past: [], future: [], dirtyCounter: 0, zoom: 0.4, showGrid: false, snap: true, cropping: null,

  load: (doc) => set({ doc, past: [], future: [], selected: [], dirtyCounter: 0, cropping: null }),

  commit: (fn, opts) => {
    const cur = get().doc;
    if (!cur) return;
    const draft = clone(cur);
    const out = fn(draft) ?? draft;
    const now = Date.now();
    // Merge rapid successive edits (e.g. slider drags, typing) into one undo step.
    const merge = opts?.merge && now - lastMergeKey < 600;
    lastMergeKey = opts?.merge ? now : 0;
    set((s) => ({
      doc: out,
      past: merge ? s.past : [...s.past, cur].slice(-HISTORY_LIMIT),
      future: [],
      dirtyCounter: s.dirtyCounter + 1,
    }));
  },

  undo: () => set((s) => {
    if (!s.past.length || !s.doc) return s;
    const prev = s.past[s.past.length - 1];
    return { doc: prev, past: s.past.slice(0, -1), future: [s.doc, ...s.future], dirtyCounter: s.dirtyCounter + 1, selected: s.selected.filter((id) => prev.layers.some((l) => l.id === id)) };
  }),
  redo: () => set((s) => {
    if (!s.future.length || !s.doc) return s;
    const next = s.future[0];
    return { doc: next, past: [...s.past, s.doc], future: s.future.slice(1), dirtyCounter: s.dirtyCounter + 1 };
  }),

  select: (ids, additive) => set((s) => {
    const doc = s.doc;
    if (!doc) return s;
    // Selecting a grouped layer selects the whole group.
    const expand = (id: string) => {
      const l = doc.layers.find((x) => x.id === id);
      if (!l) return [];
      if (l.type === "group") return [l.id, ...doc.layers.filter((x) => x.parentId === l.id).map((x) => x.id)];
      if (l.parentId) return [l.parentId, ...doc.layers.filter((x) => x.parentId === l.parentId).map((x) => x.id)];
      return [id];
    };
    const expanded = [...new Set(ids.flatMap(expand))];
    if (additive) {
      const already = expanded.every((id) => s.selected.includes(id));
      return { selected: already ? s.selected.filter((id) => !expanded.includes(id)) : [...new Set([...s.selected, ...expanded])] };
    }
    return { selected: expanded, cropping: null };
  }),

  setZoom: (z) => set({ zoom: Math.max(0.05, Math.min(4, z)) }),
  toggleGrid: () => set((s) => ({ showGrid: !s.showGrid })),
  toggleSnap: () => set((s) => ({ snap: !s.snap })),
  setCropping: (id) => set({ cropping: id }),

  updateLayers: (ids, patch, merge) => get().commit((d) => {
    d.layers = d.layers.map((l) => (ids.includes(l.id) ? { ...l, ...(typeof patch === "function" ? patch(l) : patch) } : l));
  }, { merge }),

  addLayer: (partial) => {
    const doc = get().doc!;
    const id = uid(12);
    const w = partial.width ?? Math.round(doc.width * 0.4);
    const h = partial.height ?? Math.round(doc.height * 0.2);
    const layer: DocLayer = {
      id, name: partial.name ?? partial.type, x: Math.round((doc.width - w) / 2), y: Math.round((doc.height - h) / 2),
      width: w, height: h, rotation: 0, opacity: 1, locked: false, visible: true, ...partial,
    } as DocLayer;
    get().commit((d) => { d.layers.push(layer); });
    set({ selected: [id] });
    return id;
  },

  removeSelected: () => {
    const sel = get().selected;
    if (!sel.length) return;
    get().commit((d) => {
      const doomed = new Set(sel);
      d.layers.filter((l) => l.type === "group" && doomed.has(l.id)).forEach((g) => d.layers.forEach((c) => { if (c.parentId === g.id) doomed.add(c.id); }));
      d.layers = d.layers.filter((l) => !doomed.has(l.id) || l.locked);
    });
    set({ selected: [] });
  },

  duplicateSelected: () => {
    const { doc, selected } = get();
    if (!doc || !selected.length) return;
    const idMap = new Map<string, string>();
    selected.forEach((id) => idMap.set(id, uid(12)));
    const copies = doc.layers.filter((l) => selected.includes(l.id)).map((l) => ({
      ...structuredClone(l), id: idMap.get(l.id)!, name: `${l.name} copy`, x: l.x + 24, y: l.y + 24, locked: false,
      parentId: l.parentId && idMap.has(l.parentId) ? idMap.get(l.parentId) : undefined,
    }));
    get().commit((d) => { d.layers.push(...copies); });
    set({ selected: copies.map((c) => c.id) });
  },

  reorder: (id, dir) => get().commit((d) => {
    const i = d.layers.findIndex((l) => l.id === id);
    if (i < 0) return;
    const [l] = d.layers.splice(i, 1);
    const to = dir === "top" ? d.layers.length : dir === "bottom" ? 0 : dir === "up" ? Math.min(d.layers.length, i + 1) : Math.max(0, i - 1);
    d.layers.splice(to, 0, l);
  }),

  moveTo: (id, index) => get().commit((d) => {
    const i = d.layers.findIndex((l) => l.id === id);
    if (i < 0) return;
    const [l] = d.layers.splice(i, 1);
    d.layers.splice(Math.max(0, Math.min(d.layers.length, index)), 0, l);
  }),

  group: () => {
    const { doc, selected } = get();
    if (!doc) return;
    const members = doc.layers.filter((l) => selected.includes(l.id) && l.type !== "group" && !l.parentId);
    if (members.length < 2) return;
    const gid = uid(12);
    const minX = Math.min(...members.map((m) => m.x)), minY = Math.min(...members.map((m) => m.y));
    const maxX = Math.max(...members.map((m) => m.x + m.width)), maxY = Math.max(...members.map((m) => m.y + m.height));
    get().commit((d) => {
      const topIndex = Math.max(...members.map((m) => d.layers.findIndex((l) => l.id === m.id)));
      d.layers.forEach((l) => { if (members.some((m) => m.id === l.id)) l.parentId = gid; });
      d.layers.splice(topIndex + 1, 0, { id: gid, type: "group", name: "Group", x: minX, y: minY, width: maxX - minX, height: maxY - minY, rotation: 0, opacity: 1, locked: false, visible: true });
    });
    set({ selected: [gid, ...members.map((m) => m.id)] });
  },

  ungroup: () => {
    const { doc, selected } = get();
    if (!doc) return;
    const groups = doc.layers.filter((l) => l.type === "group" && selected.includes(l.id)).map((g) => g.id);
    if (!groups.length) return;
    get().commit((d) => {
      d.layers = d.layers.filter((l) => !groups.includes(l.id)).map((l) => (l.parentId && groups.includes(l.parentId) ? { ...l, parentId: undefined } : l));
    });
    set((s) => ({ selected: s.selected.filter((id) => !groups.includes(id)) }));
  },

  align: (how) => {
    const { doc, selected } = get();
    if (!doc) return;
    const targets = doc.layers.filter((l) => selected.includes(l.id) && l.type !== "group" && !l.locked);
    if (!targets.length) return;
    // One layer → align to canvas; several → align to their bounding box.
    const box = targets.length === 1 ? { x: 0, y: 0, w: doc.width, h: doc.height } : {
      x: Math.min(...targets.map((t) => t.x)), y: Math.min(...targets.map((t) => t.y)),
      w: Math.max(...targets.map((t) => t.x + t.width)) - Math.min(...targets.map((t) => t.x)),
      h: Math.max(...targets.map((t) => t.y + t.height)) - Math.min(...targets.map((t) => t.y)),
    };
    get().commit((d) => {
      d.layers = d.layers.map((l) => {
        if (!targets.some((t) => t.id === l.id)) return l;
        const n = { ...l };
        if (how === "left") n.x = box.x;
        if (how === "center") n.x = Math.round(box.x + (box.w - l.width) / 2);
        if (how === "right") n.x = box.x + box.w - l.width;
        if (how === "top") n.y = box.y;
        if (how === "middle") n.y = Math.round(box.y + (box.h - l.height) / 2);
        if (how === "bottom") n.y = box.y + box.h - l.height;
        return n;
      });
    });
  },
}));

export const FONT_CHOICES = ["Inter", "Geist", "Manrope", "DM Sans", "Plus Jakarta Sans", "Outfit", "Poppins", "Montserrat", "Lato",
  "Bricolage Grotesque", "Space Grotesk", "Sora", "Archivo", "Work Sans", "Playfair Display", "DM Serif Display", "Fraunces",
  "Libre Baskerville", "Cormorant Garamond", "Bebas Neue", "Oswald", "Caveat"];

const loadedFonts = new Set<string>();
/** Load a Google Font into the page so Konva can measure/draw it. Resolves when ready (or after 4s). */
export function ensureFont(family?: string): Promise<void> {
  if (!family || loadedFonts.has(family) || typeof document === "undefined") return Promise.resolve();
  loadedFonts.add(family);
  const id = `gf-${family.replace(/\s+/g, "-")}`;
  // The @font-face rules must exist BEFORE document.fonts.load() is called, otherwise it matches
  // nothing and canvas text silently falls back. So: wait for the stylesheet, then load the faces.
  const sheetReady = new Promise<void>((resolve) => {
    const existing = document.getElementById(id) as HTMLLinkElement | null;
    if (existing) return resolve();
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    // Weights only: requesting an italic axis makes Google reject families that have no italics.
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}:wght@400;600;700&display=swap`;
    link.onload = () => resolve();
    link.onerror = () => resolve(); // offline or unknown family → system fallback
    document.head.appendChild(link);
  });
  return Promise.race([
    sheetReady.then(() => Promise.all([document.fonts.load(`400 24px "${family}"`), document.fonts.load(`700 24px "${family}"`)])).then(() => undefined),
    new Promise<void>((r) => setTimeout(r, 6000)),
  ]);
}
