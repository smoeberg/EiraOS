import { useCallback, useEffect, useMemo, useState } from "react";
import {
  advanceJourney,
  consumeSessionFromUrl,
  fetchDashboard,
  planIntent,
  type Dashboard,
  type Journey,
  type PlannedIntent,
  type TrustItem,
} from "./api";
import { AuthButton } from "./AuthButton";
import { EmptyState } from "./EmptyState";
import { fetchGraphContext, type GraphContext } from "./graph";
import {
  prioritizeItems,
  toHeroPrompt,
  trustLine,
  type Cluster,
  type ScoredItem,
} from "./prioritize";
import { RelationTreeView } from "./RelationTree";
import { fallbackWhyBullets } from "./why";
import { WhyFold } from "./WhyFold";

type ConfirmState = {
  item: TrustItem;
  prompt: string;
  primaryLabel: string;
};

function formatDateDa(): string {
  return new Date().toLocaleDateString("da-DK", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function firstName(greeting: string): string {
  const m = greeting.match(/Hej\s+(\S+)/i);
  return m?.[1] ?? greeting;
}

export default function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [planned, setPlanned] = useState<PlannedIntent | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [openCluster, setOpenCluster] = useState<string | null>(null);
  const [snoozed, setSnoozed] = useState<Set<string>>(new Set());
  const [whyOpen, setWhyOpen] = useState(false);
  const [graphContext, setGraphContext] = useState<GraphContext | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setDashboard(await fetchDashboard());
    } catch {
      setError("Kan ikke nå EIRA API — start backend på port 8765");
    }
  }, []);

  useEffect(() => {
    try {
      consumeSessionFromUrl();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Login fejlede");
    }
    load();
  }, [load]);

  const visibleItems = useMemo(() => {
    if (!dashboard) return [];
    return dashboard.trust_items.filter((i) => !snoozed.has(i.id));
  }, [dashboard, snoozed]);

  const view = useMemo(() => {
    if (!dashboard) return null;
    return prioritizeItems(visibleItems, dashboard.focus);
  }, [dashboard, visibleItems]);

  const hero = view?.hero ?? null;

  useEffect(() => {
    if (!hero || !dashboard) {
      setGraphContext(null);
      return;
    }

    let cancelled = false;
    const item = hero.item;

    fetchGraphContext({
      objectId: item.object_id,
      title: item.title,
      summary: item.summary,
      sources: item.sources,
      focus: dashboard.focus,
      trustScore: item.trust_score,
    })
      .then((ctx) => {
        if (!cancelled) setGraphContext(ctx);
      })
      .catch(() => {
        if (!cancelled) {
          setGraphContext({
            tree: null,
            why_bullets: fallbackWhyBullets(item, dashboard.focus),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [hero, dashboard]);

  const whyBullets = graphContext?.why_bullets.length
    ? graphContext.why_bullets
    : hero
      ? fallbackWhyBullets(hero.item, dashboard?.focus ?? "")
      : [];

  async function handlePlan(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setLoading(true);
    setPlanned(null);
    try {
      setPlanned(await planIntent(input.trim()));
    } catch {
      setError("Intent plan fejlede");
    } finally {
      setLoading(false);
    }
  }

  async function handleAdvance(journey: Journey) {
    try {
      await advanceJourney(journey.id);
      await load();
    } catch {
      setError("Kunne ikke afslutte journey-trin");
    }
  }

  function openHeroConfirm(heroItem: ScoredItem) {
    setConfirm({
      item: heroItem.item,
      prompt: toHeroPrompt(heroItem.item, heroItem.kind),
      primaryLabel: heroItem.kind === "approval" ? "Godkend" : "Fortsæt",
    });
  }

  function handleSnoozeHero() {
    if (!hero) return;
    setSnoozed((prev) => new Set(prev).add(hero.item.id));
    setConfirm(null);
    setWhyOpen(false);
  }

  function toggleCluster(cluster: Cluster) {
    const key = cluster.kind;
    setOpenCluster((prev) => (prev === key ? null : key));
  }

  const isClear = !hero && (view?.clusters.length ?? 0) === 0;

  if (error && !dashboard) {
    return (
      <div className="shell">
        <p className="error">{error}</p>
      </div>
    );
  }

  if (!dashboard || !view) {
    return (
      <div className="shell shell--loading">
        <p className="text-faint">Indlæser…</p>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">EIRA</span>
        <div className="topbar-right">
          <div className="topbar-context">
            <span className="status-dot" aria-hidden />
            <span>{dashboard.state}</span>
            <span className="text-faint">Fokus: {dashboard.focus}</span>
          </div>
          <AuthButton actorId={dashboard.actor_id} onAuthChange={load} />
        </div>
      </header>

      <main className="main">
        <section className="greeting fade-in">
          <h1 className="greeting-name">Hej {firstName(dashboard.greeting)}</h1>
          <p className="greeting-meta">
            {formatDateDa()} · {dashboard.focus}
          </p>
        </section>

        {isClear ? (
          <EmptyState />
        ) : hero ? (
          <section className="hero fade-in" aria-label="Prioriteret handling">
            <h2 className="hero-question">{toHeroPrompt(hero.item, hero.kind)}</h2>
            <p className="hero-summary">{hero.item.summary}</p>
            <p className="hero-trust">{trustLine(hero.item)}</p>

            <WhyFold
              open={whyOpen}
              bullets={whyBullets}
              onToggle={() => setWhyOpen((v) => !v)}
            />

            {graphContext?.tree && (
              <RelationTreeView tree={graphContext.tree} />
            )}

            <div className="hero-actions">
              <button
                type="button"
                className="btn-primary"
                onClick={() => openHeroConfirm(hero)}
              >
                {hero.kind === "approval" ? "Godkend" : "Fortsæt"}
              </button>
              <div className="hero-secondary">
                <button type="button" className="link-btn">
                  Se det først
                </button>
                <span className="dot-sep">·</span>
                <button type="button" className="link-btn" onClick={handleSnoozeHero}>
                  Ikke nu
                </button>
              </div>
            </div>
          </section>
        ) : null}

        {view.clusters.length > 0 && (
          <section className="clusters" aria-label="Øvrige opgaver">
            {view.clusters.map((cluster) => {
              const open = openCluster === cluster.kind;
              return (
                <div key={cluster.kind} className="cluster">
                  <button
                    type="button"
                    className="cluster-row"
                    aria-expanded={open}
                    onClick={() => toggleCluster(cluster)}
                  >
                    <span className="cluster-label">
                      {cluster.label}
                      {cluster.hint && (
                        <span className="cluster-hint"> · {cluster.hint}</span>
                      )}
                    </span>
                    <span className="cluster-chevron" aria-hidden>
                      {open ? "⌄" : "›"}
                    </span>
                  </button>
                  {open && (
                    <ul className="cluster-items">
                      {cluster.items.map((scored) => (
                        <li key={scored.item.id} className="cluster-item">
                          <span>{scored.item.title}</span>
                          {scored.requiresActor && (
                            <button
                              type="button"
                              className="cluster-action"
                              onClick={() => openHeroConfirm(scored)}
                            >
                              {scored.kind === "approval" ? "Godkend" : "Åbn"}
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </section>
        )}

        {dashboard.active_journeys.length > 0 && (
          <section className="journeys" aria-label="Igangværende forløb">
            {dashboard.active_journeys.map((journey) => {
              const current = journey.steps.find((s) => s.status === "pending");
              const pct = Math.round((journey.current_step / journey.total_steps) * 100);
              return (
                <article key={journey.id} className="journey">
                  <div className="journey-head">
                    <h3 className="journey-title">{journey.title}</h3>
                    <span className="journey-step">
                      {journey.current_step}/{journey.total_steps}
                    </span>
                  </div>
                  <div className="journey-bar" role="progressbar" aria-valuenow={pct}>
                    <div className="journey-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                  {current && (
                    <>
                      <p className="journey-current">
                        Trin {journey.current_step} — {current.label}
                        {current.actor_name ? ` (${current.actor_name})` : ""}
                      </p>
                      <button
                        type="button"
                        className="link-btn journey-advance"
                        onClick={() => handleAdvance(journey)}
                      >
                        Afslut trin: {current.label}
                      </button>
                    </>
                  )}
                </article>
              );
            })}
          </section>
        )}

        {error && <p className="error-inline">{error}</p>}
      </main>

      <div className="intent-dock">
        {planned && (
          <div className="intent-preview">
            <strong>
              {planned.category} / {planned.action}
            </strong>
            <span className="text-faint">
              {" "}
              ({Math.round(planned.confidence * 100)}%)
            </span>
            <p>{planned.rationale}</p>
            {planned.can_execute ? (
              <span className="intent-ok">Klar til bekræftelse</span>
            ) : (
              <span className="intent-block">{planned.block_reason}</span>
            )}
          </div>
        )}
        <form className="intent-form" onSubmit={handlePlan}>
          <span className="intent-prefix" aria-hidden>
            ⌘
          </span>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Hvad vil du opnå?"
            disabled={loading}
            aria-label="Hvad vil du opnå?"
          />
        </form>
      </div>

      {confirm && (
        <div className="sheet-backdrop" role="presentation" onClick={() => setConfirm(null)}>
          <div
            className="sheet fade-in"
            role="dialog"
            aria-labelledby="confirm-title"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="sheet-kicker" id="confirm-title">
              Bekræft handling
            </p>
            <p className="sheet-body">
              Jeg vil {confirm.primaryLabel.toLowerCase()}{" "}
              <em>{confirm.item.title}</em>. {trustLine(confirm.item)}.
            </p>
            <p className="sheet-stepup">Kræver MitID Erhverv i næste trin.</p>
            <button type="button" className="btn-primary" onClick={() => setConfirm(null)}>
              Fortsæt med MitID
            </button>
            <div className="sheet-secondary">
              <button type="button" className="link-btn" onClick={() => setConfirm(null)}>
                Vælg andet
              </button>
              <span className="dot-sep">·</span>
              <button type="button" className="link-btn" onClick={() => setConfirm(null)}>
                Annuller
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
