import { describe, expect, it } from "vitest";

import { retentionProgress } from "./retention";

describe("retentionProgress", () => {
  it("liefert null ohne retention_until", () => {
    expect(retentionProgress("2026-01-01", null)).toBeNull();
  });
  it("rechnet 50% in der Mitte", () => {
    const r = retentionProgress(
      "2026-01-01T00:00:00Z",
      "2026-01-11T00:00:00Z",
      new Date("2026-01-06T00:00:00Z"),
    );
    expect(r?.percent).toBeCloseTo(50, 0);
    expect(r?.daysLeft).toBe(5);
  });
  it("kappt bei abgelaufener Aufbewahrung auf 100% / 0 Tage", () => {
    const r = retentionProgress(
      "2026-01-01T00:00:00Z",
      "2026-01-02T00:00:00Z",
      new Date("2026-02-01T00:00:00Z"),
    );
    expect(r?.percent).toBe(100);
    expect(r?.daysLeft).toBe(0);
  });
});
