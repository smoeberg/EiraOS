const API = "";

export interface RelationTreeChild {
  id: string | null;
  label: string;
  relation_type: string;
  relation_label: string;
  source?: string;
  confidence?: number;
  verified?: boolean;
}

export interface RelationTree {
  root: { id: string; label: string; type: string };
  children: RelationTreeChild[];
}

export interface GraphContext {
  tree: RelationTree | null;
  why_bullets: string[];
}

export async function fetchGraphContext(params: {
  objectId?: string | null;
  title: string;
  summary: string;
  sources: string[];
  focus: string;
  trustScore: number;
}): Promise<GraphContext> {
  const q = new URLSearchParams();
  if (params.objectId) q.set("object_id", params.objectId);
  q.set("title", params.title);
  q.set("summary", params.summary);
  q.set("focus", params.focus);
  q.set("trust_score", String(params.trustScore));
  if (params.sources.length) q.set("sources", params.sources.join(","));

  const res = await fetch(`${API}/v1/graph/context?${q}`);
  if (!res.ok) throw new Error("Graph context unavailable");
  return res.json();
}
