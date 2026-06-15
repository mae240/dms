import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/apiClient";

const { navigate, toastError, registerFirstAdmin } = vi.hoisted(() => ({
  navigate: vi.fn(),
  toastError: vi.fn(),
  registerFirstAdmin: vi.fn(),
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("../../lib/toast", () => ({ toast: { error: toastError, success: vi.fn() } }));
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ registerFirstAdmin }) }));

import { SetupPage } from "./SetupPage";

async function fillAndSubmit() {
  await userEvent.type(screen.getByLabelText("Voller Name"), "Admin");
  await userEvent.type(screen.getByLabelText("E-Mail"), "a@b.de");
  await userEvent.type(screen.getByLabelText("Passwort"), "passwort1");
  await userEvent.click(screen.getByRole("button"));
}

describe("SetupPage", () => {
  it("leitet bei Erfolg aufs Dashboard", async () => {
    registerFirstAdmin.mockResolvedValueOnce(undefined);
    render(<SetupPage />);
    await fillAndSubmit();
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/dashboard", { replace: true }));
  });

  it("bei 409 Toast + Redirect Login", async () => {
    registerFirstAdmin.mockRejectedValueOnce(
      new ApiError(409, "already_initialized", "Es existiert bereits ein Benutzer."),
    );
    render(<SetupPage />);
    await fillAndSubmit();
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(navigate).toHaveBeenCalledWith("/login", { replace: true });
  });
});
