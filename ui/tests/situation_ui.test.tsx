import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProposalRecord } from "../src/components/SpatialCanvas";
import { SituationUI } from "../src/components/SituationUI";

type Metadata = {
  source?: string;
  expiresAt?: string | number;
  policyLabel?: string;
  policyLocked?: boolean;
  applied?: boolean;
};

function proposal(metadata: Metadata = {}): ProposalRecord {
  return {
    proposal_id: "proposal-1",
    suggested_transformation: "approve_document",
    candidate_state: {
      id: "state-1",
      version: 1,
      timestamp_ns: 1,
      type: "DocumentState",
      payload: { title: "Byggetilladelse" },
      previous_state_id: null,
      hash: "a".repeat(64),
    },
    confidence_score: 0.92,
    rationale: "Dokumentet opfylder de angivne krav.",
    ...metadata,
  } as ProposalRecord;
}

function cardFor(state: string) {
  const card = document.querySelector(`[data-state="${state}"]`);
  expect(card).not.toBeNull();
  return card as HTMLElement;
}

describe("SituationUI action cards", () => {
  it("viser aktiv tilstand og lader aktive forslag blive aktiveret", () => {
    const item = proposal({ source: "intentd", expiresAt: Date.now() + 60_000 });
    const onActivate = vi.fn();
    render(<SituationUI proposals={[item]} onActivate={onActivate} />);

    const card = cardFor("active");
    expect(within(card).getByRole("status")).toHaveTextContent("Aktiv");
    expect(within(card).getByText("intentd")).toBeVisible();
    expect(within(card).getByText("Udløber")).toBeVisible();
    const button = within(card).getByRole("button", { name: "Gennemgå forslag" });
    expect(button).toHaveAttribute("aria-disabled", "false");
    fireEvent.click(button);
    expect(onActivate).toHaveBeenCalledTimes(1);
    expect(onActivate).toHaveBeenCalledWith(item);
  });

  it("viser policy-låst tilstand og deaktiverer handlingen", () => {
    render(
      <SituationUI
        proposals={[proposal({ policyLocked: true, policyLabel: "Kræver godkendelse" })]}
      />,
    );
    const card = cardFor("locked");
    expect(within(card).getByRole("status")).toHaveTextContent("Låst af policy");
    expect(within(card).getByText("Kræver godkendelse")).toBeVisible();
    expect(within(card).getByRole("button")).toHaveAttribute("aria-disabled", "true");
    expect(within(card).getByRole("button")).toBeDisabled();
  });

  it("viser udløbet tilstand, når expiresAt er passeret", () => {
    render(<SituationUI proposals={[proposal({ expiresAt: Date.now() - 1_000 })]} />);
    const card = cardFor("expired");
    expect(within(card).getByRole("status")).toHaveTextContent("Udløbet");
    expect(within(card).getByRole("button")).toHaveAttribute("aria-disabled", "true");
    expect(within(card).getByRole("button")).toBeDisabled();
  });

  it("viser allerede anvendt tilstand og deaktiverer handlingen", () => {
    render(<SituationUI proposals={[proposal({ applied: true })]} />);
    const card = cardFor("applied");
    expect(within(card).getByRole("status")).toHaveTextContent("Allerede anvendt");
    expect(within(card).getByRole("button")).toHaveAttribute("aria-disabled", "true");
    expect(within(card).getByRole("button")).toBeDisabled();
  });

  it("kalder ikke onActivate ved klik på et deaktiveret kort", () => {
    const onActivate = vi.fn();
    render(
      <SituationUI
        proposals={[
          proposal({ policyLocked: true }),
          proposal({ proposal_id: "expired", expiresAt: Date.now() - 10 }),
          proposal({ proposal_id: "applied", applied: true }),
        ]}
        onActivate={onActivate}
      />,
    );

    for (const state of ["locked", "expired", "applied"]) {
      fireEvent.click(within(cardFor(state)).getByRole("button"));
    }
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("behandler udløbstidspunktet som udløbet ved præcis grænse", () => {
    const now = Date.now();
    render(<SituationUI proposals={[proposal({ expiresAt: now })]} />);
    expect(cardFor("expired")).toBeVisible();
  });
});
