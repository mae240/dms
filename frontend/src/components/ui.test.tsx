import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge, ProgressBar, StatusBadge } from "./ui";

describe("StatusBadge", () => {
  it("mappt ready auf success-Variante", () => {
    const { container } = render(<StatusBadge status="ready" />);
    expect(container.querySelector(".badge.success")).not.toBeNull();
  });
  it("mappt failed auf danger-Variante", () => {
    const { container } = render(<StatusBadge status="failed" />);
    expect(container.querySelector(".badge.danger")).not.toBeNull();
  });
  it("zeigt Platzhalter bei null", () => {
    render(<StatusBadge status={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("rendert die gewuenschte Variante und Inhalt", () => {
    const { container } = render(<Badge variant="warning">Review</Badge>);
    expect(container.querySelector(".badge.warning")).not.toBeNull();
    expect(screen.getByText("Review")).toBeInTheDocument();
  });
});

describe("ProgressBar", () => {
  it("begrenzt Prozent auf 0..100", () => {
    const { container } = render(<ProgressBar percent={150} />);
    const bar = container.querySelector(".progress > div") as HTMLElement;
    expect(bar.style.width).toBe("100%");
  });
});
