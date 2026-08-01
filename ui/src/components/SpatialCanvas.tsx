import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent,
} from "react";
import { ipcErrorMessage, sendIpcRequest } from "../lib/ipc";

export interface StateRecord {
  id: string;
  version: number;
  timestamp_ns: number;
  type: string;
  payload: Record<string, unknown>;
  previous_state_id: string | null;
  hash: string;
}

export interface ProposalRecord {
  proposal_id: string;
  suggested_transformation: string;
  candidate_state: StateRecord;
  confidence_score: number;
  rationale: string;
}

export interface CanvasNode {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  trust_score?: number;
  state?: StateRecord;
}

interface CanvasEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
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

function labelForState(state: StateRecord): string {
  const title = state.payload.title ?? state.payload.name ?? state.payload.label;
  return typeof title === "string" && title.trim() ? title : state.type;
}

function fallbackSnapshot(states: StateRecord[]): GraphSnapshot {
  const nodes = states.map((state, index) => ({
    id: state.id,
    label: labelForState(state),
    type: state.type,
    x: 120 + (index % 4) * 300,
    y: 100 + Math.floor(index / 4) * 220,
    state,
  }));
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

function proposalsFrom(states: StateRecord[]): ProposalRecord[] {
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
    const merged = {
      nodes: graph.nodes.map((node) => ({
        ...node,
        state: node.state ?? stateById.get(node.id),
      })),
      edges: graph.edges,
    };
    setSnapshot(merged.nodes.length || graph.edges.length ? merged : fallback);
    onProposals?.(proposalsFrom(states));
    setError(null);
    setLoading(false);
  }, [onProposals]);

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

  const nodeById = useMemo(
    () => new Map(snapshot.nodes.map((node) => [node.id, node])),
    [snapshot.nodes],
  );

  function select(node: CanvasNode) {
    setSelectedId(node.id);
    onSelect?.(node);
  }

  function onWheel(event: WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    setZoom((current) =>
      Math.min(2.4, Math.max(0.45, current * (event.deltaY > 0 ? 0.9 : 1.1))),
    );
  }

  function startPan(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    dragOrigin.current = { x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function movePan(event: ReactPointerEvent<HTMLDivElement>) {
    const previous = dragOrigin.current;
    if (!previous) return;
    setPan((current) => ({
      x: current.x + event.clientX - previous.x,
      y: current.y + event.clientY - previous.y,
    }));
    dragOrigin.current = { x: event.clientX, y: event.clientY };
  }

  function stopPan(event: ReactPointerEvent<HTMLDivElement>) {
    dragOrigin.current = null;
    if (
      typeof event.currentTarget.hasPointerCapture === "function" &&
      event.currentTarget.hasPointerCapture(event.pointerId)
    ) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function resetView() {
    setPan({ x: 0, y: 0 });
    setZoom(1);
  }

  return (
    <section className="canvas-panel" aria-label="Spatial Canvas workspace">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Levende tilstandsgraf</span>
          <h2>Spatial Canvas</h2>
        </div>
        <div className="canvas-tools" aria-label="Canvasværktøjer">
          <button type="button" onClick={() => setZoom((value) => Math.max(0.45, value - 0.15))}>
            −
          </button>
          <output aria-label="Zoomniveau">{Math.round(zoom * 100)}%</output>
          <button type="button" onClick={() => setZoom((value) => Math.min(2.4, value + 0.15))}>
            +
          </button>
          <button type="button" onClick={resetView}>Nulstil</button>
        </div>
      </div>

      <div
        className="spatial-canvas"
        data-testid="spatial-canvas"
        data-zoom={zoom.toFixed(2)}
        onWheel={onWheel}
        onPointerDown={startPan}
        onPointerMove={movePan}
        onPointerUp={stopPan}
        onPointerCancel={stopPan}
      >
        <div
          className="canvas-scene"
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
          <svg className="canvas-edges" width="1600" height="1000" aria-hidden="true">
            {snapshot.edges.map((edge) => {
              const source = nodeById.get(edge.source);
              const target = nodeById.get(edge.target);
              if (!source || !target) return null;
              return (
                <g key={edge.id}>
                  <line
                    x1={source.x + 92}
                    y1={source.y + 42}
                    x2={target.x + 92}
                    y2={target.y + 42}
                  />
                  <text
                    x={(source.x + target.x) / 2 + 92}
                    y={(source.y + target.y) / 2 + 34}
                  >
                    {edge.relation}
                  </text>
                </g>
              );
            })}
          </svg>
          {snapshot.nodes.map((node) => (
            <button
              type="button"
              key={node.id}
              className={`canvas-node${selectedId === node.id ? " canvas-node--selected" : ""}`}
              style={{ left: node.x, top: node.y }}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => select(node)}
              aria-pressed={selectedId === node.id}
              data-testid={`canvas-node-${node.id}`}
            >
              <span className="node-type">{node.type}</span>
              <strong>{node.label}</strong>
              <span className="node-meta">
                {node.state ? `v${node.state.version} · ${node.state.hash.slice(0, 8)}` : "Grafobjekt"}
              </span>
            </button>
          ))}
        </div>
        {loading && <p className="canvas-status">Indlæser tilstande…</p>}
        {!loading && snapshot.nodes.length === 0 && !error && (
          <p className="canvas-status">Ingen tilstande endnu.</p>
        )}
        {error && <p className="canvas-status canvas-status--error">{error}</p>}
      </div>
    </section>
  );
}
