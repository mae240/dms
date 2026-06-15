import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { confirmDialog, mutate, useRewrapStorage, useSetRetention, useSetLegalHold } = vi.hoisted(
  () => ({
    confirmDialog: vi.fn(),
    mutate: vi.fn(),
    useRewrapStorage: vi.fn(),
    useSetRetention: vi.fn(),
    useSetLegalHold: vi.fn(),
  }),
);
vi.mock("../../lib/confirm", () => ({ confirmDialog }));
vi.mock("./hooks", () => ({ useRewrapStorage, useSetRetention, useSetLegalHold }));

import { CompliancePage } from "./CompliancePage";

describe("CompliancePage Key-Rotation (A1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useRewrapStorage.mockReturnValue({ mutate, isPending: false, error: null });
    useSetRetention.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, error: null });
    useSetLegalHold.mockReturnValue({ mutateAsync: vi.fn(), isPending: false, error: null });
  });

  it("startet die Rotation nach Bestaetigung", async () => {
    confirmDialog.mockResolvedValueOnce(true);
    render(<CompliancePage />);
    await userEvent.click(screen.getByRole("button", { name: "Schluessel-Rotation starten" }));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1));
  });

  it("startet keine Rotation bei Abbruch", async () => {
    confirmDialog.mockResolvedValueOnce(false);
    render(<CompliancePage />);
    await userEvent.click(screen.getByRole("button", { name: "Schluessel-Rotation starten" }));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    expect(mutate).not.toHaveBeenCalled();
  });
});
