import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { WhyItMattersPanel } from "./why-it-matters-panel";
import { I18nProvider } from "@/i18n/context";

type StageKey = "plan" | "data" | "build" | "test" | "release" | "operate" | "improve";

function renderPanel(stage: StageKey, locale: "en" | "id" = "en") {
  return render(
    <I18nProvider defaultLocale={locale}>
      <WhyItMattersPanel stage={stage} />
    </I18nProvider>,
  );
}

describe("WhyItMattersPanel", () => {
  it("renders as an accessible region with heading", () => {
    renderPanel("plan");
    const region = screen.getByRole("region", { name: /why it matters/i });
    expect(region).toBeInTheDocument();
    expect(
      within(region).getByRole("heading", { name: /why it matters/i }),
    ).toBeInTheDocument();
  });

  it("renders stage-specific explanation text", () => {
    renderPanel("plan");
    const region = screen.getByRole("region", { name: /why it matters/i });
    expect(within(region).getByText(/governance/i)).toBeInTheDocument();
  });

  it("renders all five framework links as real anchors", () => {
    renderPanel("plan");
    const region = screen.getByRole("region", { name: /why it matters/i });

    const owaspLink = within(region).getByRole("link", { name: /owasp/i });
    const nistLink = within(region).getByRole("link", { name: /nist/i });
    const euLink = within(region).getByRole("link", { name: /eu ai act/i });
    const isoLink = within(region).getByRole("link", { name: /iso.*42001/i });
    const uuPdpLink = within(region).getByRole("link", { name: /uu pdp/i });

    expect(owaspLink).toHaveAttribute("href");
    expect(nistLink).toHaveAttribute("href");
    expect(euLink).toHaveAttribute("href");
    expect(isoLink).toHaveAttribute("href");
    expect(uuPdpLink).toHaveAttribute("href");
  });

  it("links open in new tab with noopener", () => {
    renderPanel("data");
    const region = screen.getByRole("region", { name: /why it matters/i });
    const links = within(region).getAllByRole("link");
    expect(links).toHaveLength(5);
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    }
  });

  it("renders different explanation per stage", () => {
    const { unmount } = renderPanel("plan");
    const planRegion = screen.getByRole("region", { name: /why it matters/i });
    const planText = planRegion.textContent;
    unmount();

    renderPanel("data");
    const dataRegion = screen.getByRole("region", { name: /why it matters/i });
    const dataText = dataRegion.textContent;

    expect(planText).not.toBe(dataText);
  });

  it("renders heading in Indonesian", () => {
    renderPanel("plan", "id");
    expect(
      screen.getByRole("heading", { name: /mengapa penting/i }),
    ).toBeInTheDocument();
  });

  it("renders Indonesian framework labels", () => {
    renderPanel("build", "id");
    const region = screen.getByRole("region", { name: /mengapa penting/i });
    expect(within(region).getByRole("link", { name: /owasp/i })).toBeInTheDocument();
    expect(within(region).getByRole("link", { name: /uu pdp/i })).toBeInTheDocument();
  });
});
