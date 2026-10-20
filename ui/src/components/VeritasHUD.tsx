export interface VeritasLayer {
  score: number;
  flags?: string[];
  manifest?: Record<string, unknown> | null;
  verified?: boolean;
}

export interface VeritasResult {
  trust_score: number;
  layers: {
    layer1: VeritasLayer;
    layer2: VeritasLayer;
    layer3: VeritasLayer;
    c2pa: VeritasLayer;
  };
  rationale: string[];
  hud_certificate?: { certificate_id?: string };
}

interface VeritasHUDProps {
  result: VeritasResult | null;
  subject?: string;
  loading?: boolean;
  error?: string | null;
}

const LAYERS: Array<[keyof VeritasResult["layers"], string]> = [
  ["layer1", "Lag 1 \u00b7 Kilde"],
  ["layer2", "Lag 2 \u00b7 QEAA"],
  ["layer3", "Lag 3 \u00b7 Proveniens"],
  ["c2pa", "C2PA \u00b7 Medie"],
];

const UNKNOWN_SCORE = -1;
const UNKNOWN_LABEL = "Ukendt";

function clampScore(score: number | undefined): number {
  if (score === undefined || isNaN(score)) {
    return UNKNOWN_SCORE;
  }
  return Math.max(0, Math.min(100, score));
}

function clampLayerScore(score: number | undefined): number {
  if (score === undefined || isNaN(score)) {
    return UNKNOWN_SCORE;
  }
  return Math.max(0, Math.min(1, score));
}

function formatScore(score: number): string {
  if (score === UNKNOWN_SCORE) {
    return UNKNOWN_LABEL;
  }
  return `${Math.round(score)}%`;
}

function formatLayerScore(score: number): string {
  if (score === UNKNOWN_SCORE) {
    return UNKNOWN_LABEL;
  }
  return `${Math.round(score * 100)}%`;
}

export function VeritasHUD({ result, subject, loading = false, error }: VeritasHUDProps) {
  if (loading) {
    return <aside className="veritas-hud hud-placeholder">Veritas analyserer\u2026</aside>;
  }
  if (error) {
    return <aside className="veritas-hud hud-placeholder hud-error">{error}</aside>;
  }
  if (!result) {
    return (
      <aside className="veritas-hud hud-placeholder">
        V\u00e6lg et objekt p\u00e5 canvas for at se Veritas-certifikatet.
      </aside>
    );
  }

  const score = clampScore(result.trust_score);
  const displayScore = formatScore(score);
  const meterValue = score === UNKNOWN_SCORE ? 0 : score;

  return (
    <aside className="veritas-hud" aria-label="Veritas HUD" data-testid="veritas-hud">
      <div className="hud-title-row">
        <div>
          <span className="eyebrow">Veritas HUD</span>
          <h2>{subject ?? "Valgt objekt"}</h2>
        </div>
        <div
          className="trust-ring"
          style={{ "--trust-score": `${meterValue * 3.6}deg` } as React.CSSProperties}
          role="meter"
          aria-label="Samlet Trust Score"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={meterValue}
        >
          <strong>{displayScore}</strong>
          <span>%</span>
        </div>
      </div>
      <div className="layer-list">
        {LAYERS.map(([key, label]) => {
          const layer = result.layers[key];
          const layerScore = clampLayerScore(layer?.score);
          const displayLayerScore = formatLayerScore(layerScore);
          const barWidth = layerScore === UNKNOWN_SCORE ? 0 : layerScore * 100;

          return (
            <div className="layer-row" key={key}>
              <div className="layer-label">
                <span>{label}</span>
                <output>{displayLayerScore}</output>
              </div>
              <div className="layer-track" aria-hidden="true">
                <span style={{ width: `${barWidth}%` }} />
              </div>
              {key === "c2pa" && (
                <small>
                  {layer?.manifest
                    ? "Manifest fundet"
                    : layer?.verified
                      ? "Mediesignatur verificeret"
                      : layer
                        ? "Intet verificeret manifest"
                        : UNKNOWN_LABEL}
                </small>
              )}
            </div>
          );
        })}
      </div>
      <details className="hud-rationale">
        <summary>Se forklaring</summary>
        <ul>
          {result.rationale.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        {result.hud_certificate?.certificate_id && (
          <code>{result.hud_certificate.certificate_id}</code>
        )}
      </details>
    </aside>
  );
}
