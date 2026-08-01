import type { ProposalRecord } from "./SpatialCanvas";

interface SituationUIProps {
  proposals: ProposalRecord[];
  onActivate?: (proposal: ProposalRecord) => void;
}

function actionLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
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
          {proposals.map((proposal) => (
            <article className="action-card" key={proposal.proposal_id}>
              <div className="action-card-head">
                <span className="action-kind">
                  {actionLabel(proposal.suggested_transformation)}
                </span>
                <span className="confidence">
                  {Math.round(proposal.confidence_score * 100)}%
                </span>
              </div>
              <h3>
                {String(
                  proposal.candidate_state.payload.title ??
                    proposal.candidate_state.payload.name ??
                    proposal.candidate_state.type,
                )}
              </h3>
              <p>{proposal.rationale}</p>
              <button type="button" onClick={() => onActivate?.(proposal)}>
                Gennemgå forslag
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
