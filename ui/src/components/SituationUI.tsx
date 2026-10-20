import type { CSSProperties } from "react";
import type { ProposalRecord } from "./SpatialCanvas";

interface SituationUIProps {
  proposals: ProposalRecord[];
  onActivate?: (proposal: ProposalRecord) => void;
}

type CardState = "active" | "low-confidence" | "unverified" | "applied";

const CONFIDENCE_THRESHOLD = 0.6;
const MISSING_RATIONALE = "Intet rationale angivet";

const STATE_PRESENTATION: Record<
  CardState,
  { label: string; description: string; color: string; background: string }
> = {
  active: {
    label: "Aktiv",
    description: "Klar til gennemgang",
    color: "var(--green, #72d6a0)",
    background: "rgba(114, 214, 160, 0.07)",
  },
  "low-confidence": {
    label: "Lav konfidens",
    description: "Skøn/provisorisk forslag — konfidensen er under 60 %",
    color: "var(--amber, #e9b767)",
    background: "rgba(233, 183, 103, 0.07)",
  },
  unverified: {
    label: "Ikke-verificeret",
    description: "Forslaget mangler en begrundelse og kræver manuel vurdering",
    color: "var(--amber, #e9b767)",
    background: "rgba(233, 183, 103, 0.05)",
  },
  applied: {
    label: "Allerede anvendt",
    description: "Kandidatens tilstand findes allerede i grafen",
    color: "var(--text-muted, #8f9aaa)",
    background: "rgba(255, 255, 255, 0.02)",
  },
};

function actionLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function getCardState(proposal: ProposalRecord): CardState {
  if (proposal.applied === true) return "applied";
  if (!proposal.rationale?.trim() || proposal.rationale.trim() === MISSING_RATIONALE) {
    return "unverified";
  }
  if (proposal.confidence_score < CONFIDENCE_THRESHOLD) return "low-confidence";
  return "active";
}

export function SituationUI({ proposals, onActivate }: SituationUIProps) {
  return (
    <section className="situation-panel" aria-labelledby="situation-heading">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Aktuel kontekst</span>
          <h2 id="situation-heading">Situation</h2>
        </div>
        <span className="situation-count">{proposals.length} forslag</span>
      </div>
      {proposals.length === 0 ? (
        <p className="empty-copy">Ingen forslag kræver din opmærksomhed.</p>
      ) : (
        <div className="action-grid">
          {proposals.map((proposal) => {
            const state = getCardState(proposal);
            const presentation = STATE_PRESENTATION[state];
            const canActivate = state === "active";
            const cardStyle: CSSProperties = {
              borderColor: presentation.color,
              background: presentation.background,
              opacity: canActivate ? 1 : 0.82,
            };

            return (
              <article
                className={\`action-card action-card--\${state}\`}
                key={proposal.proposal_id}
                data-state={state}
                style={cardStyle}
              >
                <div className="action-card-head">
                  <span className="action-kind">
                    {actionLabel(proposal.suggested_transformation)}
                  </span>
                  <span className="confidence">
                    {Math.round(proposal.confidence_score * 100)}%
                  </span>
                </div>
                <div
                  className="action-card-state"
                  role="status"
                  style={{
                    color: presentation.color,
                    fontSize: "0.68rem",
                    fontWeight: 650,
                    marginTop: "0.6rem",
                  }}
                >
                  {presentation.label}
                </div>
                <h3>
                  {String(
                    proposal.candidate_state.payload.title ??
                      proposal.candidate_state.payload.name ??
                      proposal.candidate_state.type,
                  )}
                </h3>
                <p>{proposal.rationale?.trim() || MISSING_RATIONALE}</p>
                <dl
                  className="action-card-metadata"
                  style={{
                    display: "grid",
                    gridTemplateColumns: "auto minmax(0, 1fr)",
                    gap: "0.35rem 0.65rem",
                    margin: "0 0 0.85rem",
                    color: "var(--text-muted, #8f9aaa)",
                    fontSize: "0.66rem",
                  }}
                >
                  <dt>Kildemodel</dt>
                  <dd style={{ margin: 0, overflowWrap: "anywhere" }}>
                    {proposal.source_model?.trim() || "Ukendt model"}
                  </dd>
                  {!canActivate && (
                    <>
                      <dt>Tilstand</dt>
                      <dd style={{ margin: 0 }}>{presentation.description}</dd>
                    </>
                  )}
                </dl>
                <button
                  type="button"
                  aria-disabled={!canActivate}
                  disabled={!canActivate}
                  onClick={() => {
                    if (canActivate) onActivate?.(proposal);
                  }}
                  style={{
                    cursor: canActivate ? "pointer" : "not-allowed",
                    opacity: canActivate ? 1 : 0.55,
                  }}
                >
                  Gennemgå forslag
                </button>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
