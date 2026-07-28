import type { TrustItem, TrustLevel } from "./api";

export type ItemKind = "approval" | "followup" | "mail" | "alert" | "other";

export interface ScoredItem {
  item: TrustItem;
  kind: ItemKind;
  score: number;
  requiresActor: boolean;
}

export interface Cluster {
  kind: ItemKind;
  label: string;
  hint: string | null;
  items: ScoredItem[];
}

export interface PrioritizedView {
  hero: ScoredItem | null;
  clusters: Cluster[];
}

const KIND_LABELS: Record<ItemKind, (n: number) => string> = {
  approval: (n) => `${n} godkendelse${n === 1 ? "" : "r"}`,
  followup: (n) => `${n} opfølgning${n === 1 ? "" : "er"}`,
  mail: (n) => `${n} mail${n === 1 ? "" : "s"}`,
  alert: (n) => `${n} advarsel${n === 1 ? "" : "er"}`,
  other: (n) => `${n} anden${n === 1 ? "" : "e"} ting`,
};

function inferKind(item: TrustItem): ItemKind {
  const t = `${item.title} ${item.summary}`.toLowerCase();
  if (/godkend|underskrift|tilladelse|sign/.test(t)) return "approval";
  if (/mail|besked|svar/.test(t)) return "mail";
  if (/lever|opfølg|deadline|frist|ordre/.test(t)) return "followup";
  if (/advar|konflikt|modstrid|fejl|mangler/.test(t)) return "alert";
  return "other";
}

function requiresActor(item: TrustItem, kind: ItemKind): boolean {
  if (item.trust_level === "unconfirmed") return true;
  if (kind === "approval" && item.trust_score < 95) return true;
  if (kind === "alert") return true;
  return item.trust_score < 85;
}

function informationalOnly(item: TrustItem, kind: ItemKind): boolean {
  return (
    item.trust_level === "indisputable" &&
    !requiresActor(item, kind) &&
    kind !== "alert"
  );
}

function focusMatch(item: TrustItem, focus: string): number {
  const blob = `${item.title} ${item.summary} ${item.sources.join(" ")}`.toLowerCase();
  return blob.includes(focus.toLowerCase()) ? 1 : 0.3;
}

function trustGate(level: TrustLevel): number {
  if (level === "unconfirmed") return 0;
  if (level === "indicative") return 0.4;
  return 1;
}

function scoreItem(item: TrustItem, kind: ItemKind, focus: string): number {
  const action = requiresActor(item, kind) ? 1 : 0.2;
  const noise = informationalOnly(item, kind) ? 1 : 0;
  return (
    25 * focusMatch(item, focus) +
    25 * action +
    10 * trustGate(item.trust_level) -
    15 * noise +
    item.trust_score * 0.15
  );
}

function clusterHint(kind: ItemKind, items: ScoredItem[]): string | null {
  const urgent = items.filter((i) => i.requiresActor).length;
  if (kind === "approval" && urgent > 0) return `${urgent} kræver svar`;
  if (kind === "followup" && urgent > 0) return `${urgent} venter på dig`;
  if (kind === "mail" && items.every((i) => i.score < 40)) return "intet presserende";
  if (kind === "alert") return urgent > 0 ? "kræver afklaring" : null;
  return null;
}

export function toHeroPrompt(item: TrustItem, kind: ItemKind): string {
  const short = item.title.split(/\s+/).slice(0, 6).join(" ");
  switch (kind) {
    case "approval":
      return `Skal jeg godkende ${short.toLowerCase()}?`;
    case "followup":
      return `Skal jeg følge op på ${short.toLowerCase()}?`;
    case "mail":
      return `Skal jeg svare på ${short.toLowerCase()}?`;
    case "alert":
      return `Skal vi kigge på ${short.toLowerCase()}?`;
    default:
      return `Vil du handle på ${short.toLowerCase()}?`;
  }
}

export function trustLine(item: TrustItem): string {
  if (item.trust_level === "indisputable" || item.trust_level === "confirmed") {
    const src = item.sources.slice(0, 2).join(" · ") || "verificeret kilde";
    return `Kilde verificeret · ${src}`;
  }
  if (item.trust_level === "probable") {
    return `Baseret på ${item.sources[0] ?? "tilgængelige data"} — vil du se først?`;
  }
  return "Kræver afklaring før handling";
}

export function prioritizeItems(
  items: TrustItem[],
  focus: string,
): PrioritizedView {
  const scored: ScoredItem[] = items.map((item) => {
    const kind = inferKind(item);
    return { item, kind, score: scoreItem(item, kind, focus), requiresActor: requiresActor(item, kind) };
  });

  const eligible = scored.filter((s) => s.item.trust_level !== "unconfirmed" || s.kind === "alert");
  const sorted = [...eligible].sort((a, b) => b.score - a.score);
  const hero = sorted[0] ?? scored.sort((a, b) => b.score - a.score)[0] ?? null;

  const rest = scored.filter((s) => s.item.id !== hero?.item.id);
  const byKind = new Map<ItemKind, ScoredItem[]>();

  for (const s of rest) {
    const list = byKind.get(s.kind) ?? [];
    list.push(s);
    byKind.set(s.kind, list);
  }

  const clusters: Cluster[] = [...byKind.entries()]
    .map(([kind, kindItems]) => {
      const sortedItems = kindItems.sort((a, b) => b.score - a.score);
      return {
        kind,
        label: KIND_LABELS[kind](sortedItems.length),
        hint: clusterHint(kind, sortedItems),
        items: sortedItems,
      };
    })
    .sort((a, b) => (b.items[0]?.score ?? 0) - (a.items[0]?.score ?? 0))
    .slice(0, 4);

  return { hero, clusters };
}
