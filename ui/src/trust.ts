import type { TrustLevel } from "./api";

export function trustLabel(level: TrustLevel): string {
  const map: Record<TrustLevel, string> = {
    unconfirmed: "? Needs confirmation",
    indicative: "≈ Indicative",
    probable: "≈ Probable",
    confirmed: "✓ Confirmed",
    indisputable: "✓ Indisputable",
  };
  return map[level];
}

export function trustClass(level: TrustLevel): string {
  return `trust trust--${level}`;
}
