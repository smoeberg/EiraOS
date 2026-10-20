/**
 * Tests for canvasLayout.ts - Sprint 7 Agent 4 (Task 7.2-perf)
 * 
 * Pure function tests - no DOM, no React, just mathematics.
 */

import { describe, it, expect } from "vitest";
import {
  computeGridLayout,
  computeForceLayout,
  filterVisibleNodes,
  extractLabel,
  createGridSnapshot,
  updateLayoutIncrementally,
  DEFAULT_GRID_CONFIG,
  DEFAULT_FORCE_CONFIG,
  type CanvasNode,
  type CanvasEdge,
  type StateRecord,
  type Viewport,
} from "../canvasLayout";

// Test fixtures
const mockState = (id: string, type: string, payload: Record<string, unknown> = {}, previousStateId: string | null = null): StateRecord => ({
  id,
  version: 1,
  timestamp_ns: Date.now() * 1e6,
  type,
  payload,
  previous_state_id: previousStateId,
  hash: `hash_${id}`,
});

const mockNode = (id: string, x: number, y: number, type: string = "TestNode"): CanvasNode => ({
  id,
  label: `Label ${id}`,
  type,
  x,
  y,
});

const mockEdge = (source: string, target: string): CanvasEdge => ({
  id: `${source}:${target}`,
  source,
  target,
  relation: "connected",
});

// =============================================================================
// computeGridLayout tests
// =============================================================================

describe("computeGridLayout", () => {
  it("should place nodes in grid pattern", () => {
    const states = [
      mockState("1", "Type1"),
      mockState("2", "Type2"),
      mockState("3", "Type3"),
      mockState("4", "Type4"),
    ];

    const nodes = computeGridLayout(states, {
      ...DEFAULT_GRID_CONFIG,
      columns: 2,
      nodeWidth: 100,
      nodeHeight: 100,
      padding: 20,
    });

    expect(nodes).toHaveLength(4);
    // First row
    expect(nodes[0].x).toBe(0);
    expect(nodes[0].y).toBe(0);
    expect(nodes[1].x).toBe(120); // 100 + 20
    expect(nodes[1].y).toBe(0);
    // Second row
    expect(nodes[2].x).toBe(0);
    expect(nodes[2].y).toBe(120); // 100 + 20
    expect(nodes[3].x).toBe(120);
    expect(nodes[3].y).toBe(120);
  });

  it("should preserve state data in nodes", () => {
    const state = mockState("test-1", "TestType", { title: "Test Title" });
    const nodes = computeGridLayout([state]);

    expect(nodes[0].id).toBe("test-1");
    expect(nodes[0].type).toBe("TestType");
    expect(nodes[0].state).toBe(state);
  });

  it("should extract label from state payload", () => {
    const state = mockState("test-1", "TestType", { title: "My Title" });
    const nodes = computeGridLayout([state]);

    expect(nodes[0].label).toBe("My Title");
  });

  it("should use type as label when no title in payload", () => {
    const state = mockState("test-1", "TestType", {});
    const nodes = computeGridLayout([state]);

    expect(nodes[0].label).toBe("TestType");
  });

  it("should handle empty state array", () => {
    const nodes = computeGridLayout([]);
    expect(nodes).toHaveLength(0);
  });

  it("should be deterministic for same input", () => {
    const states = [mockState("1", "A"), mockState("2", "B"), mockState("3", "C")];
    
    const result1 = computeGridLayout(states);
    const result2 = computeGridLayout(states);

    expect(result1).toEqual(result2);
  });
});

// =============================================================================
// computeForceLayout tests
// =============================================================================

describe("computeForceLayout", () => {
  it("should place nodes within bounds", () => {
    const nodes = [
      mockNode("1", 0, 0),
      mockNode("2", 0, 0),
      mockNode("3", 0, 0),
    ];

    const result = computeForceLayout(nodes, [], DEFAULT_FORCE_CONFIG, 1600, 1000);

    result.forEach((node) => {
      expect(node.x).toBeGreaterThanOrEqual(0);
      expect(node.x).toBeLessThanOrEqual(1500); // width - 100 margin
      expect(node.y).toBeGreaterThanOrEqual(0);
      expect(node.y).toBeLessThanOrEqual(900); // height - 100 margin
    });
  });

  it("should handle empty input", () => {
    const result = computeForceLayout([], [], DEFAULT_FORCE_CONFIG);
    expect(result).toHaveLength(0);
  });

  it("should handle nodes with edges", () => {
    const nodes = [mockNode("1", 0, 0), mockNode("2", 0, 0)];
    const edges = [mockEdge("1", "2")];

    const result = computeForceLayout(nodes, edges, {
      ...DEFAULT_FORCE_CONFIG,
      iterations: 5, // Fewer iterations for faster test
    });

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("1");
    expect(result[1].id).toBe("2");
  });

  it("should be deterministic for same input", () => {
    const nodes = [mockNode("1", 0, 0), mockNode("2", 0, 0)];
    const edges = [mockEdge("1", "2")];

    const result1 = computeForceLayout(nodes, edges, {
      ...DEFAULT_FORCE_CONFIG,
      iterations: 5,
    });
    const result2 = computeForceLayout(nodes, edges, {
      ...DEFAULT_FORCE_CONFIG,
      iterations: 5,
    });

    // X and Y should be the same for same input
    expect(result1[0].x).toBe(result2[0].x);
    expect(result1[0].y).toBe(result2[0].y);
    expect(result1[1].x).toBe(result2[1].x);
    expect(result1[1].y).toBe(result2[1].y);
  });
});

// =============================================================================
// filterVisibleNodes tests
// =============================================================================

describe("filterVisibleNodes", () => {
  const viewport: Viewport = {
    x: 0,
    y: 0,
    width: 800,
    height: 600,
    zoom: 1,
  };

  it("should return all nodes when all are visible", () => {
    const nodes = [
      mockNode("1", 100, 100),
      mockNode("2", 200, 200),
      mockNode("3", 300, 300),
    ];

    const visible = filterVisibleNodes(nodes, viewport);
    expect(visible).toHaveLength(3);
  });

  it("should filter out nodes outside viewport", () => {
    const nodes = [
      mockNode("1", 100, 100),  // Visible
      mockNode("2", 200, 200),  // Visible
      mockNode("3", 1500, 1500), // Outside
    ];

    const visible = filterVisibleNodes(nodes, viewport);
    expect(visible).toHaveLength(2);
    expect(visible.map((n) => n.id)).toContain("1");
    expect(visible.map((n) => n.id)).toContain("2");
    expect(visible.map((n) => n.id)).not.toContain("3");
  });

  it("should handle zoomed out viewport", () => {
    const zoomedOutViewport: Viewport = {
      x: 0,
      y: 0,
      width: 800,
      height: 600,
      zoom: 0.5, // Zoomed out - visible area is larger
    };

    const nodes = [
      mockNode("1", 100, 100),
      mockNode("2", 200, 200),
      mockNode("3", 400, 400),
    ];

    const visible = filterVisibleNodes(nodes, zoomedOutViewport);
    // With zoom 0.5, visible area is 1600x1200 in world coords
    expect(visible).toHaveLength(3);
  });

  it("should handle panned viewport", () => {
    const pannedViewport: Viewport = {
      x: 200,
      y: 150,
      width: 800,
      height: 600,
      zoom: 1,
    };

    const nodes = [
      mockNode("1", 100, 100),  // Left of pan - partially visible
      mockNode("2", 300, 200),  // Center of pan - visible
      mockNode("3", 1000, 1000), // Far right - not visible
    ];

    const visible = filterVisibleNodes(nodes, pannedViewport);
    expect(visible.map((n) => n.id)).toContain("2");
  });

  it("should handle empty node array", () => {
    const visible = filterVisibleNodes([], viewport);
    expect(visible).toHaveLength(0);
  });

  it("should include padding for smooth transitions", () => {
    const viewportWithPadding: Viewport = {
      x: 0,
      y: 0,
      width: 800,
      height: 600,
      zoom: 1,
    };

    // Node just outside visible area but within padding
    const nodes = [
      mockNode("1", -100, 0), // Just left of viewport
    ];

    const visible = filterVisibleNodes(nodes, viewportWithPadding, 280, 180);
    // With padding of ~140, node at -100 should be visible
    expect(visible).toHaveLength(1);
  });
});

// =============================================================================
// extractLabel tests
// =============================================================================

describe("extractLabel", () => {
  it("should extract title from payload", () => {
    const state = mockState("1", "Type", { title: "My Title" });
    expect(extractLabel(state)).toBe("My Title");
  });

  it("should extract name from payload", () => {
    const state = mockState("1", "Type", { name: "My Name" });
    expect(extractLabel(state)).toBe("My Name");
  });

  it("should extract label from payload", () => {
    const state = mockState("1", "Type", { label: "My Label" });
    expect(extractLabel(state)).toBe("My Label");
  });

  it("should use type when no label field exists", () => {
    const state = mockState("1", "MyType", {});
    expect(extractLabel(state)).toBe("MyType");
  });

  it("should handle empty string title", () => {
    const state = mockState("1", "Type", { title: "   " });
    expect(extractLabel(state)).toBe("Type");
  });

  it("should handle non-string title", () => {
    const state = mockState("1", "Type", { title: 123 });
    expect(extractLabel(state)).toBe("Type");
  });
});

// =============================================================================
// createGridSnapshot tests
// =============================================================================

describe("createGridSnapshot", () => {
  it("should create nodes and edges from states", () => {
    const states = [
      mockState("1", "Type1", { title: "Node 1" }),
      mockState("2", "Type2", { title: "Node 2" }, "1"), // previous_state_id = "1"
    ];

    const snapshot = createGridSnapshot(states);

    expect(snapshot.nodes).toHaveLength(2);
    expect(snapshot.edges).toHaveLength(1);
    expect(snapshot.edges[0].source).toBe("1");
    expect(snapshot.edges[0].target).toBe("2");
    expect(snapshot.edges[0].relation).toBe("previous");
  });

  it("should handle states without previous_state_id", () => {
    const states = [
      mockState("1", "Type1"),
      mockState("2", "Type2"),
    ];

    const snapshot = createGridSnapshot(states);

    expect(snapshot.nodes).toHaveLength(2);
    expect(snapshot.edges).toHaveLength(0);
  });

  it("should handle empty states", () => {
    const snapshot = createGridSnapshot([]);
    expect(snapshot.nodes).toHaveLength(0);
    expect(snapshot.edges).toHaveLength(0);
  });
});

// =============================================================================
// updateLayoutIncrementally tests
// =============================================================================

describe("updateLayoutIncrementally", () => {
  it("should add new nodes without affecting existing positions", () => {
    const existingNodes = [
      mockNode("1", 100, 100),
      mockNode("2", 300, 100),
    ];

    const newStates = [
      mockState("3", "Type3"),
      mockState("4", "Type4"),
    ];

    const result = updateLayoutIncrementally(existingNodes, newStates, {
      ...DEFAULT_GRID_CONFIG,
      columns: 2,
      nodeWidth: 100,
      nodeHeight: 100,
      padding: 20,
    });

    expect(result).toHaveLength(4);
    // Existing nodes should keep their positions
    expect(result[0].id).toBe("1");
    expect(result[0].x).toBe(100);
    expect(result[0].y).toBe(100);
    expect(result[1].id).toBe("2");
    expect(result[1].x).toBe(300);
    expect(result[1].y).toBe(100);
    // New nodes should be placed after
    expect(result[2].id).toBe("3");
    expect(result[2].x).toBeGreaterThan(300);
  });

  it("should not modify layout when no new states", () => {
    const existingNodes = [mockNode("1", 100, 100)];
    const newStates: StateRecord[] = [];

    const result = updateLayoutIncrementally(existingNodes, newStates);

    expect(result).toBe(existingNodes);
  });

  it("should skip states that already exist", () => {
    const existingNodes = [mockNode("1", 100, 100)];
    const newStates = [
      mockState("1", "Type1"), // Already exists
      mockState("2", "Type2"), // New
    ];

    const result = updateLayoutIncrementally(existingNodes, newStates);

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("1");
    expect(result[1].id).toBe("2");
  });

  it("should handle empty existing nodes", () => {
    const newStates = [
      mockState("1", "Type1"),
      mockState("2", "Type2"),
    ];

    const result = updateLayoutIncrementally([], newStates);

    expect(result).toHaveLength(2);
  });
});

// =============================================================================
// Performance tests
// =============================================================================

describe("performance", () => {
  it("should handle 500 nodes in grid layout quickly", () => {
    const states = Array.from({ length: 500 }, (_, i) =>
      mockState(`node-${i}`, `Type${i % 5}`),
    );

    const start = performance.now();
    const nodes = computeGridLayout(states);
    const end = performance.now();

    expect(nodes).toHaveLength(500);
    // Should complete in under 100ms (loose tolerance for CI)
    expect(end - start).toBeLessThan(100);
  });

  it("should handle 500 nodes in force layout quickly", () => {
    const nodes = Array.from({ length: 500 }, (_, i) =>
      mockNode(`node-${i}`, 0, 0, `Type${i % 5}`),
    );

    const start = performance.now();
    const result = computeForceLayout(nodes, [], {
      ...DEFAULT_FORCE_CONFIG,
      iterations: 5, // Reduced for test speed
    }, 1600, 1000);
    const end = performance.now();

    expect(result).toHaveLength(500);
    // Should complete in under 100ms (loose tolerance for CI)
    // Note: Force layout is O(n^2) so this might be slower
    expect(end - start).toBeLessThan(200); // Looser tolerance for force layout
  });

  it("should filter 500 nodes quickly", () => {
    const nodes = Array.from({ length: 500 }, (_, i) =>
      mockNode(`node-${i}`, i * 100, i * 50),
    );

    const viewport: Viewport = {
      x: 0,
      y: 0,
      width: 800,
      height: 600,
      zoom: 1,
    };

    const start = performance.now();
    const visible = filterVisibleNodes(nodes, viewport);
    const end = performance.now();

    // Only nodes in viewport should be returned
    expect(visible.length).toBeLessThan(500);
    expect(end - start).toBeLessThan(10);
  });
});
