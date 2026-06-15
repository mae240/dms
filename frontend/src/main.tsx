import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { ApiError } from "./lib/apiClient";
import { AuthProvider } from "./lib/auth";
import { ConfirmContainer } from "./lib/confirm";
import { ToastContainer, toast } from "./lib/toast";
import "./index.css";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Unbekannter Fehler";
}

const queryClient = new QueryClient({
  // Jede fehlgeschlagene Mutation erzeugt automatisch einen Fehler-Toast.
  mutationCache: new MutationCache({
    onError: (error) => {
      // 401 behandelt der apiClient (Refresh/Redirect) — kein Toast noetig.
      if (error instanceof ApiError && error.status === 401) return;
      toast.error(errorMessage(error));
    },
  }),
  defaultOptions: {
    queries: {
      // Bei Authentifizierungs-/Berechtigungsfehlern nicht endlos neu versuchen.
      retry: (count, error) => {
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) return false;
        return count < 2;
      },
      staleTime: 10_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
      <ToastContainer />
      <ConfirmContainer />
    </QueryClientProvider>
  </React.StrictMode>,
);
