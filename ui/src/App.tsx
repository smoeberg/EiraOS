import { useCallback, useEffect, useState } from "react";
import {
  SpatialCanvas,
  type CanvasNode,
  type ProposalRecord,
} from "./components/SpatialCanvas";
import { IntentBar } from "./components/IntentBar";
import { SituationUI } from "./components/SituationUI";
import { TerminalPanel } from "./components/TerminalPanel";
import { VeritasHUD, type VeritasResult } from "./components/VeritasHUD";
import { ipcErrorMessage, sendIpcRequest } from "./lib/ipc";

export default function App() {
  const [selected, setSelected] = useState<CanvasNode | null>(null);
  const [proposals, setProposals] = useState<ProposalRecord[]>([]);
  const [veritas, setVeritas] = useState<VeritasResult | null>(null);
  const [veritasLoading, setVeritasLoading] = useState(false);
  const [veritasError, setVeritasError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [terminalOpen, setTerminalOpen] = useState(false);

  // Builder Mode (terminal, files, legacy apps) is policy-gated and owned by
  // intentd. Explorer is the default and the fallback whenever the mode
  // cannot be confirmed. The backend checks again before opening a shell.
  const [builderMode, setBuilderMode] = useState(false);
  useEffect(() => {
    let cancelled = false;
    sendIpcRequest<{ mode?: string }>("intentd", "presentation.mode_get", {})
      .then((state) => {
        if (!cancelled) setBuilderMode(state?.mode === "builder");
      })
      .catch(() => {
        if (!cancelled) setBuilderMode(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Ctrl+Alt+T opens or closes the terminal — only in Builder Mode.
  useEffect(() => {
    if (!builderMode) {
      setTerminalOpen(false);
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.altKey && event.key.toLowerCase() === "t") {
        event.preventDefault();
        setTerminalOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [builderMode]);

  const handleSelect = useCallback(async (node: CanvasNode | null) => {
    setSelected(node);
    setVeritas(null);
    setVeritasError(null);
    if (!node) return;
    setVeritasLoading(true);
    try {
      const payload = node.state?.payload ?? { id: node.id, title: node.label };
      const result = await sendIpcRequest<VeritasResult>(
        "veritasd",
        "veritas.evaluate",
        {
          document: {
            ...payload,
            title: node.label,
            state_hash: node.state?.hash,
          },
          claim: { text: node.label, state_id: node.id },
        },
      );
      setVeritas(result);
    } catch (error) {
      setVeritasError(ipcErrorMessage(error));
    } finally {
      setVeritasLoading(false);
    }
  }, []);

  const handleProposal = useCallback((proposal: ProposalRecord) => {
    const state = proposal.candidate_state;
    void handleSelect({
      id: state.id,
      label: String(state.payload.title ?? state.payload.name ?? state.type),
      type: state.type,
      x: 0,
      y: 0,
      state,
    });
  }, [handleSelect]);

  const refreshAfterIntent = useCallback(() => {
    setReloadKey((key) => key + 1);
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <span className="brand">EIRA</span>
          <span className="header-divider" aria-hidden />
          <span className="header-context">Spatial Workspace</span>
        </div>
        <div className="header-actions">
          {builderMode && (
            <button
              type="button"
              className="header-button"
              aria-pressed={terminalOpen}
              onClick={() => setTerminalOpen((open) => !open)}
              title="Terminal (Ctrl+Alt+T)"
            >
              Terminal
            </button>
          )}
          <div className="runtime-status">
            <span aria-hidden />
            Lokal Unix IPC
          </div>
        </div>
      </header>
      <IntentBar onExecuted={refreshAfterIntent} />
      <main className="workspace-grid">
        <SpatialCanvas key={reloadKey} onSelect={handleSelect} onProposals={setProposals} />
        <VeritasHUD
          result={veritas}
          subject={selected?.label}
          loading={veritasLoading}
          error={veritasError}
        />
        <SituationUI proposals={proposals} onActivate={handleProposal} />
      </main>
      {builderMode && terminalOpen && <TerminalPanel onClose={() => setTerminalOpen(false)} />}
    </div>
  );
}
