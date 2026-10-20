import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VeritasHUD, VeritasResult } from "../VeritasHUD";

const baseResult: VeritasResult = {
  trust_score: 85,
  layers: {
    layer1: { score: 0.9, verified: true },
    layer2: { score: 0.8, verified: true },
    layer3: { score: 0.7, verified: true },
    c2pa: { score: 1.0, manifest: { provider: "test" }, verified: true },
  },
  rationale: ["Test rationale"],
  hud_certificate: { certificate_id: "cert-123" },
};

describe("VeritasHUD", () => {
  describe("Loading state", () => {
    it("shows loading placeholder", () => {
      render(<VeritasHUD loading={true} result={null} />);
      expect(screen.getByText(/Veritas analyserer/)).toBeInTheDocument();
    });
  });

  describe("Error state", () => {
    it("shows error message with error styling", () => {
      render(<VeritasHUD error="Verificering fejlede" result={null} />);
      const errorElement = screen.getByText("Verificering fejlede");
      expect(errorElement).toBeInTheDocument();
      expect(errorElement.closest("aside")).toHaveClass("hud-error");
    });
  });

  describe("Null result state", () => {
    it("shows placeholder when no object selected", () => {
      render(<VeritasHUD result={null} />);
      expect(
        screen.getByText(/canvas/)
      ).toBeInTheDocument();
    });
  });

  describe("Trust score clamping", () => {
    it("clamps trust_score below 0 to 0", () => {
      const result: VeritasResult = {
        ...baseResult,
        trust_score: -5,
      };
      render(<VeritasHUD result={result} />);
      expect(screen.getByText("0%")).toBeInTheDocument();
    });

    it("clamps trust_score above 100 to 100", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          layer1: { score: 0.1, verified: true },
          layer2: { score: 0.1, verified: true },
          layer3: { score: 0.1, verified: true },
          c2pa: { score: 0.1, manifest: {}, verified: true },
        },
        trust_score: 150,
      };
      render(<VeritasHUD result={result} />);
      const trustRing = screen.getByLabelText("Samlet Trust Score");
      expect(within(trustRing).getByText("100%")).toBeInTheDocument();
    });

    it("handles NaN trust_score as unknown", () => {
      const result: VeritasResult = {
        ...baseResult,
        trust_score: NaN,
      };
      render(<VeritasHUD result={result} />);
      expect(screen.getByText("Ukendt")).toBeInTheDocument();
    });

    it("handles undefined trust_score as unknown", () => {
      const result: VeritasResult = {
        ...baseResult,
        trust_score: undefined as unknown as number,
      };
      render(<VeritasHUD result={result} />);
      expect(screen.getByText("Ukendt")).toBeInTheDocument();
    });
  });

  describe("Layer score clamping", () => {
    it("clamps layer score below 0 to 0%", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          ...baseResult.layers,
          layer1: { score: -0.5, verified: true },
        },
      };
      render(<VeritasHUD result={result} />);
      const layerRows = screen.getAllByText("0%");
      expect(layerRows.length).toBeGreaterThan(0);
    });

    it("clamps layer score above 1 to 100%", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          layer1: { score: 1.5, verified: true },
          layer2: { score: 0.1, verified: true },
          layer3: { score: 0.1, verified: true },
          c2pa: { score: 0.1, manifest: {}, verified: true },
        },
      };
      render(<VeritasHUD result={result} />);
      const layerRow = screen.getByText("Lag 1 · Kilde").parentElement;
      expect(within(layerRow!).getByText("100%")).toBeInTheDocument();
    });

    it("handles NaN layer score as unknown", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          layer1: { score: NaN, verified: true },
          layer2: { score: 0.8, verified: true },
          layer3: { score: 0.7, verified: true },
          c2pa: { score: 1.0, manifest: {}, verified: true },
        },
      };
      render(<VeritasHUD result={result} />);
      const layerRow = screen.getByText("Lag 1 · Kilde").parentElement;
      expect(within(layerRow!).getByText("Ukendt")).toBeInTheDocument();
    });

    it("handles undefined layer score as unknown", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          layer1: { score: undefined as unknown as number, verified: true },
          layer2: { score: 0.8, verified: true },
          layer3: { score: 0.7, verified: true },
          c2pa: { score: 1.0, manifest: {}, verified: true },
        },
      };
      render(<VeritasHUD result={result} />);
      const layerRow = screen.getByText("Lag 1 · Kilde").parentElement;
      expect(within(layerRow!).getByText("Ukendt")).toBeInTheDocument();
    });
  });

  describe("Missing layer handling", () => {
    it("shows unknown for missing layer1", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          layer1: { score: NaN },
          layer2: { score: 0.8, verified: true },
          layer3: { score: 0.7, verified: true },
          c2pa: { score: 1.0, manifest: {}, verified: true },
        },
      };
      render(<VeritasHUD result={result} />);
      const layerRow = screen.getByText("Lag 1 · Kilde").parentElement;
      expect(within(layerRow!).getByText("Ukendt")).toBeInTheDocument();
    });

    it("shows unknown for missing C2PA layer", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          layer1: { score: 0.9, verified: true },
          layer2: { score: 0.8, verified: true },
          layer3: { score: 0.7, verified: true },
          c2pa: { score: NaN },
        },
      };
      render(<VeritasHUD result={result} />);
      const c2paRow = screen.getByText("C2PA · Medie").parentElement;
      expect(within(c2paRow!).getByText("Ukendt")).toBeInTheDocument();
    });

    it("shows unknown C2PA label when c2pa layer has no manifest or verified", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          layer1: { score: 0.9, verified: true },
          layer2: { score: 0.8, verified: true },
          layer3: { score: 0.7, verified: true },
          c2pa: { score: 0.5 },
        },
      };
      render(<VeritasHUD result={result} />);
      expect(screen.getByText("Intet verificeret manifest")).toBeInTheDocument();
    });
  });

  describe("C2PA manifest states", () => {
    it("shows manifest fundet when manifest exists", () => {
      render(<VeritasHUD result={baseResult} />);
      expect(screen.getByText("Manifest fundet")).toBeInTheDocument();
    });

    it("shows Mediesignatur verificeret when verified but no manifest", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          ...baseResult.layers,
          c2pa: { score: 1.0, manifest: null, verified: true },
        },
      };
      render(<VeritasHUD result={result} />);
      expect(screen.getByText("Mediesignatur verificeret")).toBeInTheDocument();
    });

    it("shows Intet verificeret manifest when not verified and no manifest", () => {
      const result: VeritasResult = {
        ...baseResult,
        layers: {
          ...baseResult.layers,
          c2pa: { score: 0.5, manifest: null, verified: false },
        },
      };
      render(<VeritasHUD result={result} />);
      expect(screen.getByText("Intet verificeret manifest")).toBeInTheDocument();
    });
  });

  describe("Rationale and certificate", () => {
    it("shows rationale list", () => {
      render(<VeritasHUD result={baseResult} />);
      expect(screen.getByText("Se forklaring")).toBeInTheDocument();
      expect(screen.getByText("Test rationale")).toBeInTheDocument();
    });

    it("shows certificate ID when present", () => {
      render(<VeritasHUD result={baseResult} />);
      expect(screen.getByText("cert-123")).toBeInTheDocument();
    });

    it("does not show certificate ID when missing", () => {
      const result: VeritasResult = {
        ...baseResult,
        hud_certificate: undefined,
      };
      render(<VeritasHUD result={result} />);
      expect(screen.queryByText("cert-123")).not.toBeInTheDocument();
    });
  });

  describe("Subject display", () => {
    it("shows custom subject when provided", () => {
      render(<VeritasHUD result={baseResult} subject="Test Object" />);
      expect(screen.getByText("Test Object")).toBeInTheDocument();
    });

    it("shows default subject when not provided", () => {
      render(<VeritasHUD result={baseResult} />);
      expect(screen.getByText("Valgt objekt")).toBeInTheDocument();
    });
  });

  describe("Component structure", () => {
    it("has correct test id", () => {
      render(<VeritasHUD result={baseResult} />);
      expect(screen.getByTestId("veritas-hud")).toBeInTheDocument();
    });

    it("has correct aria labels", () => {
      render(<VeritasHUD result={baseResult} />);
      expect(screen.getByLabelText("Veritas HUD")).toBeInTheDocument();
      expect(screen.getByLabelText("Samlet Trust Score")).toBeInTheDocument();
    });
  });

  describe("All layers present", () => {
    it("renders all four layers", () => {
      render(<VeritasHUD result={baseResult} />);
      expect(screen.getByText("Lag 1 \u00b7 Kilde")).toBeInTheDocument();
      expect(screen.getByText("Lag 2 \u00b7 QEAA")).toBeInTheDocument();
      expect(screen.getByText("Lag 3 \u00b7 Proveniens")).toBeInTheDocument();
      expect(screen.getByText("C2PA \u00b7 Medie")).toBeInTheDocument();
    });
  });
});
