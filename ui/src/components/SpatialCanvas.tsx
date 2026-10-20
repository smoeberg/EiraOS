import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent,
} from "react";
import React from "react";
import { ipcErrorMessage, sendIpcRequest } from "../lib/ipc";
import {
  filterVisibleNodes,
  createGridSnapshot,
  updateLayoutIncrementally,
  DEFAULT_GRID_CONFIG,
  type Viewport,
  type CanvasNode,
  type CanvasEdge,
  type StateRecord,
} from "../lib/canvasLayout";

export interface ProposalRecord {
  proposal_id: string;
  suggested_transformation: string;
  candidate_state: StateRecord;
  confidence_score: number;
  rationale: string;
  source_model: string;
  /** Derived from the current graph, not persisted in ProposalState. */
  applied?: boolean;
}

interface StateListResult {
  states: StateRecord[];
  count: number;
}

interface GraphSnapshot {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}

interface SpatialCanvasProps {
  pollIntervalMs?: number;
  onSelect?: (node: CanvasNode | null) => void;
  onProposals?: (proposals: ProposalRecord[]) => void;
}

/**
 * Memoized node component to prevent unnecessary re-renders.
 * Only re-renders when props change.
 */
const CanvasNodeComponent = React.memo(function CanvasNodeComponent({
  node,
  isSelected,
  onClick,
  onPointerDown,
}: {
  node: CanvasNode;
  isSelected: boolean;
  onClick: () => void;
  onPointerDown: (event: ReactPointerEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      className={`canvas-node${isSelected ? " canvas-node--selected" : ""}`}
      style={{ left: node.x, top: node.y }}
      onPointerDown={onPointerDown}
      onClick={onClick}
      aria-pressed={isSelected}
      data-testid={`canvas-node-${node.id}`}
    >
      <span className="node-type">{node.type}</span>
      <strong>{node.label}</strong>
      <span className="node-meta">
        {node.state ? `v${node.state.version} 3 ${node.state.hash.slice(0, 8)}` : "Grafobjekt"}
      </span>
    </button>
  );
});

CanvasNodeComponent.displayName = "CanvasNodeComponent";

/**
 * Memoized edge component to prevent unnecessary re-renders.
 */
const CanvasEdgeComponent = React.memo(function CanvasEdgeComponent({
  edge,
  sourceNode,
  targetNode,
}: {
  edge: CanvasEdge;
  sourceNode: CanvasNode | null;
  targetNode: CanvasNode | null;
}) {
  if (!sourceNode || !targetNode) return null;

  return (
    <g key={edge.id}>
      <line
        x1={sourceNode.x + 92}
        y1={sourceNode.y + 42}
        x2={targetNode.x + 92}
        y2={targetNode.y + 42}
      />
      <text
        x={(sourceNode.x + targetNode.x) / 2 + 92}
        y={(sourceNode.y + targetNode.y) / 2 + 34}
      >
        {edge.relation}
      </text>
    </g>
  );
});

CanvasEdgeComponent.displayName = "CanvasEdgeComponent";

/**
 * Memoized SVG edges container to prevent re-rendering when nodes don't change.
 */
const CanvasEdgesContainer = React.memo(function CanvasEdgesContainer({
  edges,
  nodeById,
}: {
  edges: CanvasEdge[];
  nodeById: Map<string, CanvasNode>;
}) {
  return (
    <svg className="canvas-edges" width="1600" height="1000" aria-hidden="true">
      {edges.map((edge) => (
        <CanvasEdgeComponent
          key={edge.id}
          edge={edge}
          sourceNode={nodeById.get(edge.source) || null}
          targetNode={nodeById.get(edge.target) || null}
        />
      ))}
    </svg>
  );
});

CanvasEdgesContainer.displayName = "CanvasEdgesContainer";

/**
 * Memoized nodes container with virtualization support.
 * Only renders nodes that are visible in the viewport.
 */
const CanvasNodesContainer = React.memo(function CanvasNodesContainer({
  nodes,
  selectedId,
  viewport,
  onNodeClick,
  onNodePointerDown,
}: {
  nodes: CanvasNode[];
  selectedId: string | null;
  viewport: Viewport;
  onNodeClick: (node: CanvasNode) => void;
  onNodePointerDown: (event: ReactPointerEvent<HTMLButtonElement>, node: CanvasNode) => void;
}) {
  // Filter nodes to only visible ones (virtualization)
  const visibleNodes = useMemo(
    () => filterVisibleNodes(nodes, viewport, 280, 180),
    [nodes, viewport.x, viewport.y, viewport.width, viewport.height, viewport.zoom],
  );

  const handleClick = useCallback(
    (n: CanvasNode) => () => onNodeClick(n),
    [onNodeClick],
  );

  const handlePointerDown = useCallback(
    (n: CanvasNode) => (event: ReactPointerEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      onNodePointerDown(event, n);
    },
    [onNodePointerDown],
  );

  return (
    <>
      {visibleNodes.map((n) => (
        <CanvasNodeComponent
          key={n.id}
          node={n}
          isSelected={selectedId === n.id}
          onClick={handleClick(n)}
          onPointerDown={handlePointerDown(n)}
        />
      ))}
    </>
  );
});

CanvasNodesContainer.displayName = "CanvasNodesContainer";

/**
 * Create fallback snapshot using grid layout
 */
function fallbackSnapshot(states: StateRecord[]): GraphSnapshot {
  return createGridSnapshot(states, DEFAULT_GRID_CONFIG);
}

/**
 * Convert states to proposals
 */
function usePrefersReducedMotion(): boolean {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(mediaQuery.matches);
    update();
    mediaQuery.addEventListener("change", update);
    return () => mediaQuery.removeEventListener("change", update);
  }, []);

  return reducedMotion;
}

function proposalsFrom(states: StateRecord[], existingStateIds: Set<string>): ProposalRecord[] {
  return states.flatMap((state) => {
    if (state.type !== "ProposalState") return [];
    const payload = state.payload as Partial<ProposalRecord>;
    if (!payload.candidate_state || !payload.suggested_transformation) return [];
    return [
      {
        proposal_id: payload.proposal_id ?? state.id,
        suggested_transformation: payload.suggested_transformation,
        candidate_state: payload.candidate_state,
        confidence_score: Number(payload.confidence_score ?? 0),
        rationale: payload.rationale ?? "Intet rationale angivet",
        source_model: payload.source_model ?? "Ukendt model",
        applied: existingStateIds.has(payload.candidate_state.id),
      },
    ];
  });
}

export function SpatialCanvas({
  pollIntervalMs = 1_500,
  onSelect,
  onProposals,
}: SpatialCanvasProps) {
  const [snapshot, setSnapshot] = useState<GraphSnapshot>({ nodes: [], edges: [] });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragOrigin = useRef<{ x: number; y: number } | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  // Memoize viewport for virtualization
  const viewport = useMemo<Viewport>(() => ({
    x: pan.x,
    y: pan.y,
    width: window.innerWidth || 800,
    height: window.innerHeight || 600,
    zoom,
  }), [pan.x, pan.y, zoom]);

  // Memoize nodeById map to prevent recreation on every render
  const nodeById = useMemo(
    () => new Map(snapshot.nodes.map((node) => [node.id, node])),
    [snapshot.nodes],
  );

  // Stable callback for refresh
  const refresh = useCallback(async () => {
    const [statesResult, graphResult] = await Promise.allSettled([
      sendIpcRequest<StateListResult>("stated", "state.list", { limit: 2_000 }),
      sendIpcRequest<GraphSnapshot>("graphd", "graph.spatial_snapshot", {
        limit: 2_000,
      }),
    ]);
    if (statesResult.status === "rejected" && graphResult.status === "rejected") {
      throw statesResult.reason;
    }

    const states =
      statesResult.status === "fulfilled" ? statesResult.value.states : [];
    const fallback = fallbackSnapshot(states);
    const graph = graphResult.status === "fulfilled" ? graphResult.value : fallback;
    const stateById = new Map(states.map((state) => [state.id, state]));
    
    // Incrementally update layout - only compute positions for new nodes
    const merged = {
      nodes: updateLayoutIncrementally(
        snapshot.nodes,
        states,
        DEFAULT_GRID_CONFIG,
      ).map((n) => ({
        ...n,
        state: n.state ?? stateById.get(n.id),
      })),
      edges: graph.edges,
    };
    
    setSnapshot(merged.nodes.length || graph.edges.length ? merged : fallback);
    onProposals?.(proposalsFrom(states, new Set(merged.nodes.map((node) => node.id))));
    setError(null);
    setLoading(false);
  }, [snapshot.nodes, onProposals]);

  useEffect(() => {
    let active = true;
    const load = () => {
      refresh().catch((reason: unknown) => {
        if (active) {
          setError(ipcErrorMessage(reason));
          setLoading(false);
        }
      });
    };
    load();
    const timer = window.setInterval(load, Math.max(500, pollIntervalMs));
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [pollIntervalMs, refresh]);

  // Memoized handlers for pan and zoom
  const onWheel = useCallback(
    (event: WheelEvent<HTMLDivElement>) => {
      event.preventDefault();
      setZoom((current) =>
        Math.min(2.4, Math.max(0.45, current * (event.deltaY > 0 ? 0.9 : 1.1))),
      );
    },
    [],
  );

  const startPan = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      dragOrigin.current = { x: event.clientX, y: event.clientY };
      event.currentTarget.setPointerCapture?.(event.pointerId);
    },
    [],
  );

  const movePan = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const previous = dragOrigin.current;
      if (!previous) return;
      setPan((current) => ({
        x: current.x + event.clientX - previous.x,
        y: current.y + event.clientY - previous.y,
      }));
      dragOrigin.current = { x: event.clientX, y: event.clientY };
    },
    [],
  );

  const stopPan = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      dragOrigin.current = null;
      if (
        typeof event.currentTarget.hasPointerCapture === "function" &&
        event.currentTarget.hasPointerCapture(event.pointerId)
      ) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    },
    [],
  );

  const resetView = useCallback(() => {
    setPan({ x: 0, y: 0 });
    setZoom(1);
  }, []);

  // Memoized handler for node selection
  const handleNodeClick = useCallback(
    (n: CanvasNode) => {
      setSelectedId(n.id);
      onSelect?.(n);
    },
    [onSelect],
  );

  const handleNodePointerDown = useCallback(
    (_event: ReactPointerEvent<HTMLButtonElement>, _n: CanvasNode) => {
      _event.stopPropagation();
    },
    [],
  );

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    switch (event.key) {
      case "ArrowLeft":
        event.preventDefault();
        setPan((current) => ({ ...current, x: current.x - 40 }));
        break;
      case "ArrowRight":
        event.preventDefault();
        setPan((current) => ({ ...current, x: current.x + 40 }));
        break;
      case "ArrowUp":
        event.preventDefault();
        setPan((current) => ({ ...current, y: current.y - 40 }));
        break;
      case "ArrowDown":
        event.preventDefault();
        setPan((current) => ({ ...current, y: current.y + 40 }));
        break;
      case "+":
      case "PageUp":
        event.preventDefault();
        setZoom((current) => Math.min(2.4, current + 0.15));
        break;
      case "-":
      case "PageDown":
        event.preventDefault();
        setZoom((current) => Math.max(0.45, current - 0.15));
        break;
      case "0":
        event.preventDefault();
        resetView();
        break;
      default:
        break;
    }
  }

  return (
    <section className="canvas-panel" aria-label="Spatial Canvas workspace">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Levende tilstandsgraf</span>
          <h2>Spatial Canvas</h2>
        </div>
        <div className="canvas-tools" aria-label="Canvasvrktojer">
          <button type="button" onClick={() => setZoom((value) => Math.max(0.45, value - 0.15))}>
            
          </button>
          <output
            aria-label="Zoomniveau"
            aria-live="polite"
            style={{ color: "#f4f6f8" }}
          >
            {Math.round(zoom * 100)}%
          </output>
          <button
            type="button"
            onClick={() => setZoom((value) => Math.min(2.4, value + 0.15))}
            style={{ color: "#f4f6f8" }}
          >
            +
          </button>
          <button type="button" onClick={resetView} style={{ color: "#f4f6f8" }}>
            Nulstil
          </button>
        </div>
      </div>

      <div
        className="spatial-canvas"
        data-testid="spatial-canvas"
        data-zoom={zoom.toFixed(2)}
        role="application"
        tabIndex={0}
        aria-label="Spatial Canvas, interaktiv tilstandsgraf"
        aria-describedby="spatial-canvas-instructions"
        onKeyDown={onKeyDown}
        onWheel={onWheel}
        onPointerDown={startPan}
        onPointerMove={movePan}
        onPointerUp={stopPan}
        onPointerCancel={stopPan}
      >
        <span
          id="spatial-canvas-instructions"
          style={{
            position: "absolute",
            width: 1,
            height: 1,
            padding: 0,
            margin: -1,
            overflow: "hidden",
            clip: "rect(0, 0, 0, 0)",
            whiteSpace: "nowrap",
            border: 0,
          }}
        >
          Brug piletaster til at panorere, plus eller PageUp til at zoome ind, minus eller
          PageDown til at zoome ud, og 0 til at nulstille visningen.
        </span>
        <div
          className="canvas-scene"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transition: reducedMotion ? "none" : undefined,
          }}
        >
          <CanvasEdgesContainer edges={snapshot.edges} nodeById={nodeById} />
          
          <CanvasNodesContainer
            nodes={snapshot.nodes}
            selectedId={selectedId}
            viewport={viewport}
            onNodeClick={handleNodeClick}
            onNodePointerDown={handleNodePointerDown}
          />
        </div>
        {loading && <p className="canvas-status">Indlser tilstande</p>}
        {!loading && error && (
          <p role="alert" className="canvas-status canvas-status--error">
            {error}
          </p>
        )}
        {!loading && snapshot.nodes.length === 0 && !error && (
          <p className="canvas-status">Ingen tilstande endnu.</p>
        )}
      </div>
    </section>
  );
}

// Re-export types from canvasLayout for App.tsx
export type { CanvasNode, CanvasEdge, StateRecord };
