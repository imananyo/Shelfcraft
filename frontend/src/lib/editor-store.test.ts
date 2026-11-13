import { beforeEach, describe, expect, it } from "vitest";
import { useEditor } from "./editor-store";
import type { EditorDoc } from "./types";

const base = (): EditorDoc => ({
  width: 1000, height: 800, background: "#ffffff",
  layers: [
    { id: "a", type: "rect", name: "A", x: 10, y: 10, width: 100, height: 50, rotation: 0, opacity: 1, locked: false, visible: true, fill: "#000" },
    { id: "b", type: "text", name: "B", x: 300, y: 200, width: 200, height: 40, rotation: 0, opacity: 1, locked: false, visible: true, text: "Hi" },
    { id: "c", type: "rect", name: "C", x: 0, y: 0, width: 1000, height: 800, rotation: 0, opacity: 1, locked: true, visible: true, fill: "#eee" },
  ],
});
const s = () => useEditor.getState();

describe("editor store", () => {
  beforeEach(() => s().load(base()));

  it("undo/redo restores exact previous states", () => {
    s().updateLayers(["a"], { x: 500 });
    expect(s().doc!.layers[0].x).toBe(500);
    s().undo();
    expect(s().doc!.layers[0].x).toBe(10);
    s().redo();
    expect(s().doc!.layers[0].x).toBe(500);
  });

  it("merges rapid edits into one undo step", () => {
    s().updateLayers(["a"], { opacity: 0.9 }, true);
    s().updateLayers(["a"], { opacity: 0.5 }, true);
    s().updateLayers(["a"], { opacity: 0.2 }, true);
    s().undo();
    expect(s().doc!.layers[0].opacity).toBe(1);
  });

  it("adds, duplicates and deletes layers; locked layers survive delete", () => {
    const id = s().addLayer({ type: "ellipse", fill: "#f00" });
    expect(s().selected).toEqual([id]);
    s().duplicateSelected();
    expect(s().doc!.layers).toHaveLength(5);
    s().select(["c"]);
    s().removeSelected();
    expect(s().doc!.layers.find((l) => l.id === "c")).toBeTruthy();
  });

  it("groups and ungroups; selecting a member selects the whole group", () => {
    s().select(["a", "b"]);
    s().group();
    const g = s().doc!.layers.find((l) => l.type === "group")!;
    expect(g).toBeTruthy();
    expect(g.x).toBe(10);
    expect(g.width).toBe(490);
    s().select(["a"]);
    expect(new Set(s().selected)).toEqual(new Set([g.id, "a", "b"]));
    s().ungroup();
    expect(s().doc!.layers.some((l) => l.type === "group")).toBe(false);
    expect(s().doc!.layers.every((l) => !l.parentId)).toBe(true);
  });

  it("aligns a single layer to the canvas and multiple layers to their bounds", () => {
    s().select(["a"]);
    s().align("center");
    expect(s().doc!.layers[0].x).toBe(450);
    s().select(["a", "b"]);
    s().align("left");
    expect(s().doc!.layers.filter((l) => ["a", "b"].includes(l.id)).map((l) => l.x)).toEqual([300, 300]);
  });

  it("reorders layers (z-index)", () => {
    s().reorder("a", "top");
    expect(s().doc!.layers.at(-1)!.id).toBe("a");
    s().reorder("a", "bottom");
    expect(s().doc!.layers[0].id).toBe("a");
  });

  it("increments the autosave counter on every committed change", () => {
    const before = s().dirtyCounter;
    s().updateLayers(["b"], { text: "Hello" });
    expect(s().dirtyCounter).toBe(before + 1);
  });
});
