import type { CSSProperties } from "react";
import type { ProposalRecord } from "./SpatialCanvas";

interface SituationUIProps {
  proposals: ProposalRecord[];
  onActivate?: (proposal: ProposalRecord) => void;
}

type ProposalWithActionMetadata = ProposalRecord & {
  source?: string | null;
  sourceLabel?: string | null;
  source_label?: string | null;
  origin?: string | null;
  expiresAt?: string | number | null;
  expires_at?: string | number | null;
  policyLabel?: string | null;
  policy_label?: string | null;
  policyLocked?: boolean;
  policy_locked?: boolean;
  applied?: boolean;
  used?: boolean;
  status?: string | null;
};

type CardState = "active" | "locked" | "expired" | "applied";

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
  locked: {
    label: "Låst af policy",
    description: "Kan ikke aktiveres under gældende policy",
    color: "var(--amber, #e9b767)",
    background: "rgba(233, 183, 103, 0.07)",
  },
  expired: {
    label: "Udløbet",
    description: "Forslagets gyldighed er udløbet",
    color: "var(--red, #f28585)",
    background: "rgba(242, 133, 133, 0.06)",
  },
  applied: {
    label: "Allerede anvendt",
    description: "Dette forslag er allerede anvendt",
    color: "var(--text-muted, #8f9aaa)",
    background: "rgba(255, 255, 255, 0.02)",
  },
};

function actionLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function nonEmptyString(...values: unknown[]): string | undefined {
  return values.find(
    (value): value is string => typeof value === "string" && value.trim().length > 0,
  );
}

function expiryTimestamp(value: string | number | null | undefined): number | undefined {
  if (typeof value !== "string" && typeof value !== "number") return undefined;
  if (typeof value === "string" && value.trim() === "") return undefined;
  const timestamp = typeof value === "number" ? value : Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : undefined;
}

function expiryLabel(timestamp: number): string {
  return new Intl.DateTimeFormat("da-DK", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(timestamp);
}

function getCardState(proposal: ProposalWithActionMetadata, now: number): CardState {
  const status = proposal.status?.toLowerCase().replaceAll("-", "_");
  if (proposal.applied === true || proposal.used === true || status === "applied" || status === "used") {
    return "applied";
  }
  if (
    proposal.policyLocked === true ||
    proposal.policy_locked === true ||
    status === "locked" ||
    status === "policy_locked"
  ) {
    return "locked";
  }
  const expiresAt = expiryTimestamp(proposal.expiresAt ?? proposal.expires_at);
  if (expiresAt !== undefined && expiresAt <= now) return "expired";
  return "active";
}

export function SituationUI({ proposals, onActivate }: SituationUIProps) {
  // Expiry is intentionally evaluated during render; no timer or background task is needed.
  const now = Date.now();

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
            const enriched = proposal as ProposalWithActionMetadata;
            const state = getCardState(enriched, now);
            const presentation = STATE_PRESENTATION[state];
            const canActivate = state === "active";
            const expiresAt = expiryTimestamp(enriched.expiresAt ?? enriched.expires_at);
            const source = nonEmptyString(
              enriched.sourceLabel,
              enriched.source_label,
              enriched.source,
              enriched.origin,
            );
            const policyLabel = nonEmptyString(enriched.policyLabel, enriched.policy_label);
            const cardStyle: CSSProperties = {
              borderColor: presentation.color,
              background: presentation.background,
              opacity: canActivate ? 1 : 0.82,
            };

            return (
              <article
                className={`action-card action-card--${state}`}
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
                <p>{proposal.rationale}</p>
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
                  <dt>Kilde</dt>
                  <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{source ?? "Ukendt kilde"}</dd>
                  {expiresAt !== undefined && (
                    <>
                      <dt>Udløber</dt>
                      <dd style={{ margin: 0 }}>{expiryLabel(expiresAt)}</dd>
                    </>
                  )}
                  {policyLabel && (
                    <>
                      <dt>Policy</dt>
                      <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{policyLabel}</dd>
                    </>
                  )}
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
