import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvalScreen } from "./eval-screen";
import { I18nProvider } from "@/i18n/context";

function renderEval(locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <EvalScreen />
    </I18nProvider>,
  );
}

describe("EvalScreen", () => {
  it("renders datasets and runs sections", () => {
    renderEval();
    expect(screen.getByRole("heading", { name: /datasets/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /runs/i })).toBeInTheDocument();
  });

  it("renders permission leak summary", () => {
    renderEval();
    expect(screen.getByText(/permission leak summary/i)).toBeInTheDocument();
  });

  it("renders action buttons", () => {
    renderEval();
    expect(screen.getByRole("button", { name: /new dataset/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run evaluation/i })).toBeInTheDocument();
  });

  it("renders in Indonesian", () => {
    renderEval("id");
    expect(screen.getByRole("heading", { name: /dataset/i })).toBeInTheDocument();
    expect(screen.getByText(/ringkasan kebocoran izin/i)).toBeInTheDocument();
  });

  it("has accessible heading", () => {
    renderEval();
    expect(screen.getByRole("heading", { name: /eval lab/i })).toBeInTheDocument();
  });
});
