import { describe, expect, it } from "vitest";

import { ApiError } from "./apiClient";
import { roleAtLeast } from "./can";

describe("roleAtLeast", () => {
  it("respektiert die Rollen-Hierarchie", () => {
    expect(roleAtLeast("owner", "admin")).toBe(true);
    expect(roleAtLeast("admin", "editor")).toBe(true);
    expect(roleAtLeast("editor", "editor")).toBe(true);
    expect(roleAtLeast("viewer", "editor")).toBe(false);
    expect(roleAtLeast(null, "viewer")).toBe(false);
    expect(roleAtLeast(undefined, "viewer")).toBe(false);
  });
});

describe("ApiError", () => {
  it("traegt Status, Code und Nachricht", () => {
    const err = new ApiError(403, "forbidden", "Kein Zugriff");
    expect(err.status).toBe(403);
    expect(err.code).toBe("forbidden");
    expect(err.message).toBe("Kein Zugriff");
    expect(err).toBeInstanceOf(Error);
  });
});
