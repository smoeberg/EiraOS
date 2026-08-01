from app.core.state import State, ProposalState
from app.core.constraint import Constraint
from app.core.store import StateStore
from app.core.event import EventBus
from app.core.knowledge import KnowledgeRepository, KnowledgeEntry
from app.core.transformation import IntegratedEngine
from app.daemons import graphd, stated
from app.ipc.client import IpcClient


def test_full_state_runtime_flow():
    store = StateStore(":memory:")
    bus = EventBus()
    knowledge_repo = KnowledgeRepository()
    engine = IntegratedEngine(store, bus)

    events = []
    bus.subscribe("state.transformed", lambda e: events.append(e))

    # 1. Base state
    state1 = State(type="DocumentState", payload={"title": "Test Doc", "status": "DRAFT"})
    store.append(state1)

    # 2. Candidate state update
    state2 = State(
        type="DocumentState",
        payload={"title": "Test Doc", "status": "APPROVED"},
        previous_state_id=state1.id,
        version=2
    )

    proposal = ProposalState(
        suggested_transformation="approve_document",
        candidate_state=state2,
        confidence_score=0.95,
        source_model="mistral",
        rationale="All constraints met"
    )

    constraint = Constraint(
        id="status_check",
        expression="payload['status'] == 'APPROVED'",
        error_message="Status must be APPROVED"
    )

    # 3. Apply proposal through engine
    result_state = engine.apply_proposal(proposal, [constraint], {})

    assert result_state.id == state2.id
    assert len(events) == 1
    assert events[0].payload["state_id"] == str(state2.id)

    # 4. Knowledge proof entry
    entry = KnowledgeEntry(
        state_id=state2.id,
        transformation_name="approve_document",
        explanation="Approved by rule check",
        proof_type="CEL_CONSTRAINT"
    )
    knowledge_repo.add_entry(entry)
    proofs = knowledge_repo.get_proofs_for_state(state2.id)
    assert len(proofs) == 1
    assert proofs[0].transformation_name == "approve_document"


def test_spatial_snapshot_reads_state_through_stated(monkeypatch):
    base = State(
        type="DocumentState",
        timestamp_ns=1,
        payload={"title": "Base"},
    )
    proposal = State(
        type="ProposalState",
        version=2,
        timestamp_ns=2,
        previous_state_id=base.id,
        payload={"title": "Forslag"},
    )
    store = StateStore(":memory:")
    store.append(base)
    store.append(proposal)
    monkeypatch.setattr(stated, "_store", store)

    def call(_self, method, params):
        assert method == "state.list"
        return stated.state_list(params)

    monkeypatch.setattr(IpcClient, "call", call)
    snapshot = graphd.graph_spatial_snapshot({"limit": 10})

    assert [node["id"] for node in snapshot["nodes"]] == [
        str(base.id),
        str(proposal.id),
    ]
    assert snapshot["edges"] == [
        {
            "id": f"{base.id}:{proposal.id}",
            "source": str(base.id),
            "target": str(proposal.id),
            "relation": "proposes",
        }
    ]
