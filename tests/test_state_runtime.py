from uuid import uuid4
from app.core.state import State, ProposalState
from app.core.constraint import Constraint
from app.core.store import StateStore
from app.core.event import EventBus
from app.core.knowledge import KnowledgeRepository, KnowledgeEntry
from app.core.timed import TimedScheduler, TimedTrigger
from app.core.transformation import IntegratedEngine


def test_full_state_runtime_flow():
    store = StateStore(":memory:")
    bus = EventBus()
    knowledge_repo = KnowledgeRepository()
    scheduler = TimedScheduler(bus)
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

