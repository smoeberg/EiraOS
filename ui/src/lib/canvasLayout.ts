/**
 * Canvas Layout Utilities - Sprint 7 Agent 4 (Task 7.2-perf)
 * 
 * Pure functions for computing node positions in SpatialCanvas.
 * Designed to be testable without DOM dependencies.
 */

/**
 * State record from the backend - represents a state in the system
 */
export interface StateRecord {
  id: string;
  version: number;
  timestamp_ns: number;
  type: string;
  payload: Record<string, unknown>;
  previous_state_id: string | null;
  hash: string;
}

/**
 * Canvas node - visual representation of a state
 */
export interface CanvasNode {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  trust_score?: number;
  state?: StateRecord;
}

/**
 * Canvas edge - connection between nodes
 */
export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
}

/**
 * Viewport boundaries for virtualization
 */
export interface Viewport {
  x: number;
  y: number;
  width: number;
  height: number;
  zoom: number;
}

/**
 * Grid layout configuration
 */
export interface GridLayoutConfig {
  nodeWidth: number;
  nodeHeight: number;
  padding: number;
  columns: number;
}

/**
 * Default grid layout configuration
 */
export const DEFAULT_GRID_CONFIG: GridLayoutConfig = {
  nodeWidth: 280,
  nodeHeight: 180,
  padding: 40,
  columns: 4,
};

/**
 * Simple force-directed layout configuration
 */
export interface ForceLayoutConfig {
  repulsion: number;
  stiffness: number;
  damping: number;
  iterations: number;
}

/**
 * Default force layout configuration
 */
export const DEFAULT_FORCE_CONFIG: ForceLayoutConfig = {
  repulsion: 1000,
  stiffness: 0.1,
  damping: 0.8,
  iterations: 20,
};

/**
 * Computes node position using a simple grid layout.
 * Nodes are arranged in rows and columns based on their index.
 * Pure function - deterministic output for same input.
 */
export function computeGridLayout(
  states: StateRecord[],
  config: GridLayoutConfig = DEFAULT_GRID_CONFIG,
): CanvasNode[] {
  return states.map((state, index) => {
    const col = index % config.columns;
    const row = Math.floor(index / config.columns);
    
    return {
      id: state.id,
      label: extractLabel(state),
      type: state.type,
      x: col * (config.nodeWidth + config.padding),
      y: row * (config.nodeHeight + config.padding),
      state,
    };
  });
}

/**
 * Computes a force-directed layout for nodes.
 * Simple physics simulation: repulsion between all nodes, attraction along edges.
 * Pure function - deterministic for same input and seed.
 */
export function computeForceLayout(
  nodes: CanvasNode[],
  edges: CanvasEdge[],
  config: ForceLayoutConfig = DEFAULT_FORCE_CONFIG,
  width: number = 1600,
  height: number = 1000,
): CanvasNode[] {
  if (nodes.length === 0) return [];

  // Initialize positions randomly within bounds
  const positions = new Map<string, { x: number; y: number }>();
  const centerX = width / 2;
  const centerY = height / 2;
  
  nodes.forEach((node, index) => {
    // Deterministic pseudo-random based on index
    const angle = (index * 0.618033988749895) % (2 * Math.PI);
    const radius = Math.min(width, height) * 0.3 * (0.5 + index * 0.01);
    positions.set(node.id, {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    });
  });

  // Build edge connections for attraction
  const connections = new Map<string, string[]>();
  edges.forEach((edge) => {
    if (!connections.has(edge.source)) {
      connections.set(edge.source, []);
    }
    connections.get(edge.source)!.push(edge.target);
    if (!connections.has(edge.target)) {
      connections.set(edge.target, []);
    }
    connections.get(edge.target)!.push(edge.source);
  });

  // Simple force simulation
  const result = new Map<string, { x: number; y: number }>(
    positions,
  );

  for (let iteration = 0; iteration < config.iterations; iteration++) {
    const forces = new Map<string, { fx: number; fy: number }>();

    // Initialize forces
    nodes.forEach((node) => {
      forces.set(node.id, { fx: 0, fy: 0 });
    });

    // Repulsion between all nodes
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const id1 = nodes[i].id;
        const id2 = nodes[j].id;
        const p1 = positions.get(id1)!;
        const p2 = positions.get(id2)!;

        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance > 0) {
          const force = config.repulsion / (distance * distance);
          const fx = (dx / distance) * force;
          const fy = (dy / distance) * force;

          forces.get(id1)!.fx -= fx;
          forces.get(id1)!.fy -= fy;
          forces.get(id2)!.fx += fx;
          forces.get(id2)!.fy += fy;
        }
      }
    }

    // Attraction along edges
    edges.forEach((edge) => {
      const sourcePos = positions.get(edge.source);
      const targetPos = positions.get(edge.target);
      
      if (sourcePos && targetPos) {
        const dx = targetPos.x - sourcePos.x;
        const dy = targetPos.y - sourcePos.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance > 0) {
          const force = config.stiffness * distance;
          const fx = (dx / distance) * force;
          const fy = (dy / distance) * force;

          forces.get(edge.source)!.fx += fx;
          forces.get(edge.source)!.fy += fy;
          forces.get(edge.target)!.fx -= fx;
          forces.get(edge.target)!.fy -= fy;
        }
      }
    });

    // Apply forces with damping
    nodes.forEach((node) => {
      const force = forces.get(node.id)!;
      const pos = result.get(node.id)!;
      
      pos.x += force.fx * config.damping;
      pos.y += force.fy * config.damping;

      // Keep within bounds
      pos.x = Math.max(0, Math.min(width - 100, pos.x));
      pos.y = Math.max(0, Math.min(height - 100, pos.y));
    });
  }

  // Convert to CanvasNode array
  return nodes.map((node) => ({
    ...node,
    x: Math.round(result.get(node.id)!.x),
    y: Math.round(result.get(node.id)!.y),
  }));
}

/**
 * Filters nodes to only those visible in the current viewport.
 * Pure function for virtualization.
 */
export function filterVisibleNodes(
  nodes: CanvasNode[],
  viewport: Viewport,
  nodeWidth: number = 280,
  nodeHeight: number = 180,
): CanvasNode[] {
  const { x, y, width, height, zoom } = viewport;
  
  // Calculate visible bounds in world coordinates
  const visibleLeft = x / zoom;
  const visibleTop = y / zoom;
  const visibleRight = (x + width) / zoom;
  const visibleBottom = (y + height) / zoom;

  // Add padding to avoid popping
  const padding = Math.max(nodeWidth, nodeHeight) * 0.5;

  return nodes.filter((node) => {
    const nodeRight = node.x + nodeWidth;
    const nodeBottom = node.y + nodeHeight;

    return (
      node.x - padding < visibleRight &&
      nodeRight + padding > visibleLeft &&
      node.y - padding < visibleBottom &&
      nodeBottom + padding > visibleTop
    );
  });
}

/**
 * Extracts a label from a state record.
 * Pure function for consistent labeling.
 */
export function extractLabel(state: StateRecord): string {
  const title = state.payload.title ?? state.payload.name ?? state.payload.label;
  return typeof title === "string" && title.trim() ? title : state.type;
}

/**
 * Creates a simple grid snapshot from state records.
 * Pure function for fallback when graphd is unavailable.
 */
export function createGridSnapshot(
  states: StateRecord[],
  config: GridLayoutConfig = DEFAULT_GRID_CONFIG,
): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
  const nodes = computeGridLayout(states, config);
  
  const edges = states.flatMap((state) =>
    state.previous_state_id
      ? [
          {
            id: `${state.previous_state_id}:${state.id}`,
            source: state.previous_state_id,
            target: state.id,
            relation: "previous",
          },
        ]
      : [],
  );

  return { nodes, edges };
}

/**
 * Incrementally updates node positions when new states are added.
 * Only re-computes positions for new nodes, preserving existing positions.
 * This prevents full re-layout on every state change.
 */
export function updateLayoutIncrementally(
  existingNodes: CanvasNode[],
  newStates: StateRecord[],
  config: GridLayoutConfig = DEFAULT_GRID_CONFIG,
): CanvasNode[] {
  const existingIds = new Set(existingNodes.map((n) => n.id));
  const newStatesOnly = newStates.filter((s) => !existingIds.has(s.id));

  if (newStatesOnly.length === 0) {
    return existingNodes;
  }

  // Compute positions for new states only
  const newNodes = computeGridLayout(newStatesOnly, config);

  // Find the last existing node to continue layout
  const lastX = existingNodes.length > 0
    ? Math.max(...existingNodes.map((n) => n.x))
    : 0;

  // Offset new nodes to continue from last position
  const offsetX = existingNodes.length > 0
    ? lastX + config.nodeWidth + config.padding
    : 0;

  // Apply offset to new nodes
  const offsetNodes = newNodes.map((node, index) => {
    const col = index % config.columns;
    const row = Math.floor(index / config.columns);
    return {
      ...node,
      x: offsetX + col * (config.nodeWidth + config.padding),
      y: row * (config.nodeHeight + config.padding),
    };
  });

  return [...existingNodes, ...offsetNodes];
}
