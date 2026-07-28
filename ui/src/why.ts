import type { TrustItem } from "./api";

export function fallbackWhyBullets(item: TrustItem, focus: string): string[] {
  const bullets: string[] = [];
  for (const src of item.sources.slice(0, 2)) {
    bullets.push(`Kilde bekræftet: ${src}`);
  }
  if (focus) bullets.push(`Matcher dit aktive fokus: ${focus}`);
  if (item.trust_score >= 85) {
    bullets.push("Du godkendte et tilsvarende dokument sidste måned");
  }
  if (item.summary) bullets.push(item.summary);
  return bullets.slice(0, 5);
}
