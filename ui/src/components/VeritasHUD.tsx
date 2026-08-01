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
  ["layer1", "Lag 1 · Kilde"],
  ["layer2", "Lag 2 · QEAA"],
  ["layer3", "Lag 3 · Proveniens"],
  ["c2pa", "C2PA · Medie"],
];

export function VeritasHUD({ result, subject, loading = false, error }: VeritasHUDProps) {
  if (loading) {
    return <aside className="veritas-hud hud-placeholder">Veritas analyserer…</aside>;
  }
  if (error) {
    return <aside className="veritas-hud hud-placeholder hud-error">{error}</aside>;
  }
  if (!result) {
    return (
      <aside className="veritas-hud hud-placeholder">
        Vælg et objekt på canvas for at se Veritas-certifikatet.
      </aside>
    );
  }

  const score = Math.max(0, Math.min(100, result.trust_score));
  return (
    <aside className="veritas-hud" aria-label="Veritas HUD" data-testid="veritas-hud">
      <div className="hud-title-row">
        <div>
          <span className="eyebrow">Veritas HUD</span>
          <h2>{subject ?? "Valgt objekt"}</h2>
        </div>
        <div
          className="trust-ring"
          style={{ "--trust-score": `${score * 3.6}deg` } as React.CSSProperties}
          role="meter"
          aria-label="Samlet Trust Score"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={score}
        >
          <strong>{Math.round(score)}</strong>
          <span>%</span>
        </div>
      </div>
      <div className="layer-list">
        {LAYERS.map(([key, label]) => {
          const layer = result.layers[key];
          const layerScore = Math.round(Math.max(0, Math.min(1, layer.score)) * 100);
          return (
            <div className="layer-row" key={key}>
              <div className="layer-label">
                <span>{label}</span>
                <output>{layerScore}%</output>
              </div>
              <div className="layer-track" aria-hidden="true">
                <span style={{ width: `${layerScore}%` }} />
              </div>
              {key === "c2pa" && (
                <small>
                  {layer.manifest
                    ? "Manifest fundet"
                    : layer.verified
                      ? "Mediesignatur verificeret"
                      : "Intet verificeret manifest"}
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
