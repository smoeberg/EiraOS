import { useCallback, useState } from "react";
import {
  SpatialCanvas,
  type CanvasNode,
  type ProposalRecord,
} from "./components/SpatialCanvas";
import { SituationUI } from "./components/SituationUI";
import { VeritasHUD, type VeritasResult } from "./components/VeritasHUD";
import { ipcErrorMessage, sendIpcRequest } from "./lib/ipc";

export default function App() {
  const [selected, setSelected] = useState<CanvasNode | null>(null);
  const [proposals, setProposals] = useState<ProposalRecord[]>([]);
  const [veritas, setVeritas] = useState<VeritasResult | null>(null);
  const [veritasLoading, setVeritasLoading] = useState(false);
  const [veritasError, setVeritasError] = useState<string | null>(null);

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

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <span className="brand">EIRA</span>
          <span className="header-divider" aria-hidden />
          <span className="header-context">Spatial Workspace</span>
        </div>
        <div className="runtime-status">
          <span aria-hidden />
          Lokal Unix IPC
        </div>
      </header>
      <main className="workspace-grid">
        <SpatialCanvas onSelect={handleSelect} onProposals={setProposals} />
        <VeritasHUD
          result={veritas}
          subject={selected?.label}
          loading={veritasLoading}
          error={veritasError}
        />
        <SituationUI proposals={proposals} onActivate={handleProposal} />
      </main>
    </div>
  );
}
