import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProposalRecord } from "../src/components/SpatialCanvas";
import { SituationUI } from "../src/components/SituationUI";

type Metadata = Partial<Pick<ProposalRecord, "confidence_score" | "rationale" | "source_model" | "applied">>;

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
    source_model: "intentd",
    applied: false,
    ...metadata,
  };
}

function cardFor(state: string) {
  const card = document.querySelector(\`[data-state="\${state}"]\`);
  expect(card).not.toBeNull();
  return card as HTMLElement;
}

describe("SituationUI action cards", () => {
  it("viser aktiv tilstand og tillader aktivering", () => {
    const item = proposal();
    const onActivate = vi.fn();
    render(<SituationUI proposals={[item]} onActivate={onActivate} />);

    const card = cardFor("active");
    expect(within(card).getByRole("status")).toHaveTextContent("Aktiv");
    expect(within(card).getByText("intentd")).toBeVisible();
    const button = within(card).getByRole("button", { name: "Gennemgå forslag" });
    expect(button).toHaveAttribute("aria-disabled", "false");
    fireEvent.click(button);
    expect(onActivate).toHaveBeenCalledTimes(1);
    expect(onActivate).toHaveBeenCalledWith(item);
  });

  it("viser lav konfidens under tærsklen og deaktiverer handlingen", () => {
    render(<SituationUI proposals={[proposal({ confidence_score: 0.59 })]} />);
    const card = cardFor("low-confidence");
    expect(within(card).getByRole("status")).toHaveTextContent("Lav konfidens");
    expect(within(card).getByText(/under 60 %/)).toBeVisible();
    expect(within(card).getByRole("button")).toHaveAttribute("aria-disabled", "true");
    expect(within(card).getByRole("button")).toBeDisabled();
  });

  it("viser manglende rationale som ikke-verificeret", () => {
    render(<SituationUI proposals={[proposal({ rationale: "Intet rationale angivet" })]} />);
    const card = cardFor("unverified");
    expect(within(card).getByRole("status")).toHaveTextContent("Ikke-verificeret");
    expect(within(card).getByText("Intet rationale angivet")).toBeVisible();
    expect(within(card).getByRole("button")).toBeDisabled();
  });

  it("viser allerede anvendt tilstand og deaktiverer handlingen", () => {
    render(<SituationUI proposals={[proposal({ applied: true })]} />);
    const card = cardFor("applied");
    expect(within(card).getByRole("status")).toHaveTextContent("Allerede anvendt");
    expect(within(card).getByRole("button")).toHaveAttribute("aria-disabled", "true");
    expect(within(card).getByRole("button")).toBeDisabled();
  });

  it("kalder ikke onActivate ved klik på deaktiverede kort", () => {
    const onActivate = vi.fn();
    render(
      <SituationUI
        proposals={[
          proposal({ proposal_id: "low", confidence_score: 0.2 }),
          proposal({ proposal_id: "unverified", rationale: "Intet rationale angivet" }),
          proposal({ proposal_id: "applied", applied: true }),
        ]}
        onActivate={onActivate}
      />,
    );

    for (const state of ["low-confidence", "unverified", "applied"]) {
      fireEvent.click(within(cardFor(state)).getByRole("button"));
    }
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("behandler konfidens på præcis 0.6 som aktiv", () => {
    render(<SituationUI proposals={[proposal({ confidence_score: 0.6 })]} />);
    expect(cardFor("active")).toBeVisible();
    expect(within(cardFor("active")).getByRole("button")).toBeEnabled();
  });
});
