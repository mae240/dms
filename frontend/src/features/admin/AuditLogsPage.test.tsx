import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditLogOut, Page } from "../../types/api";

const { useAuditLogs } = vi.hoisted(() => ({ useAuditLogs: vi.fn() }));
vi.mock("./hooks", async () => {
  const actual = await vi.importActual<typeof import("./hooks")>("./hooks");
  return { ...actual, useAuditLogs };
});

import { AuditLogsPage } from "./AuditLogsPage";

function makeLog(over: Partial<AuditLogOut>): AuditLogOut {
  return {
    id: "11111111-2222-3333-4444-555555555555",
    actor_user_id: null,
    action: "document.upload",
    entity_type: "document",
    entity_id: null,
    project_id: null,
    ip_address: null,
    metadata: null,
    created_at: "2026-06-15T10:00:00Z",
    ...over,
  };
}

function mockPage(items: AuditLogOut[]) {
  const page: Page<AuditLogOut> = { items, total: items.length, limit: 25, offset: 0 };
  useAuditLogs.mockReturnValue({ data: page, isPending: false, error: null });
}

describe("AuditLogsPage Metadaten (A3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("zeigt JSON-Metadaten beim Aufklappen", async () => {
    mockPage([makeLog({ metadata: { size: 42, name: "vertrag.pdf" } })]);
    render(<AuditLogsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Details anzeigen" }));
    expect(screen.getByText(/"size": 42/)).toBeInTheDocument();
    expect(screen.getByText(/"name": "vertrag.pdf"/)).toBeInTheDocument();
  });

  it("zeigt 'Keine Details' wenn metadata null ist", async () => {
    mockPage([makeLog({ metadata: null })]);
    render(<AuditLogsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Details anzeigen" }));
    expect(screen.getByText("Keine Details")).toBeInTheDocument();
  });
});
