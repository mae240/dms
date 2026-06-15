import { useMutation } from "@tanstack/react-query";

import { api, setAccessToken } from "../../lib/apiClient";
import { toast } from "../../lib/toast";
import type { TokenOut } from "../../types/api";

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api.post<TokenOut>("/auth/change-password", body),
    onSuccess: (data) => {
      // Aktuelle Sitzung mit frischem Access-Token weiterführen.
      setAccessToken(data.access_token);
      toast.success("Passwort geaendert. Andere Sitzungen wurden abgemeldet.");
    },
  });
}
