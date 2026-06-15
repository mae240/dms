// Zentraler API-Client: Bearer-Access-Token (in-memory) + automatischer
// 401->Refresh->Retry. Das Refresh-Token liegt im httpOnly-Cookie und wird
// vom Browser automatisch mitgesendet.

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let accessToken: string | null = null;
let onAuthLost: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
export function getAccessToken(): string | null {
  return accessToken;
}
export function setOnAuthLost(cb: () => void): void {
  onAuthLost = cb;
}

async function parseError(res: Response): Promise<ApiError> {
  let code = "error";
  let message = res.statusText || "Fehler";
  let details: unknown = null;
  try {
    const body = await res.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? null;
    }
  } catch {
    /* keine JSON-Antwort */
  }
  return new ApiError(res.status, code, message, details);
}

async function rawRequest(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  return fetch(`${BASE}${path}`, { ...init, headers });
}

async function tryRefresh(): Promise<boolean> {
  const res = await fetch(`${BASE}/auth/refresh`, { method: "POST" });
  if (!res.ok) return false;
  const data = (await res.json()) as { access_token: string };
  accessToken = data.access_token;
  return true;
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  let res = await rawRequest(path, init);

  if (res.status === 401 && retry) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await rawRequest(path, init);
    } else {
      accessToken = null;
      onAuthLost?.();
      throw await parseError(res);
    }
  }

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function refreshAccessToken(): Promise<boolean> {
  return tryRefresh();
}

function parseXhrError(xhr: XMLHttpRequest): ApiError {
  let code = "error";
  let message = xhr.statusText || "Fehler";
  let details: unknown = null;
  try {
    const body = JSON.parse(xhr.responseText);
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details ?? null;
    }
  } catch {
    /* keine JSON-Antwort */
  }
  return new ApiError(xhr.status, code, message, details);
}

// Upload via XHR, um echten Fortschritt zu erhalten (fetch kann das nicht).
// Bei 401 wird einmal das Token erneuert und erneut gesendet.
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress?: (percent: number) => void,
  retry = true,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError(0, "aborted", "Upload abgebrochen"));
      return;
    }
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}${path}`);
    if (accessToken) xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }
    const onAbort = () => xhr.abort();
    if (signal) signal.addEventListener("abort", onAbort);
    const cleanup = () => {
      if (signal) signal.removeEventListener("abort", onAbort);
    };
    xhr.onabort = () => {
      cleanup();
      reject(new ApiError(0, "aborted", "Upload abgebrochen"));
    };
    xhr.onload = () => {
      cleanup();
      if (xhr.status === 401 && retry) {
        tryRefresh().then((ok) => {
          if (ok) {
            uploadWithProgress<T>(path, form, onProgress, false, signal).then(resolve, reject);
          } else {
            accessToken = null;
            onAuthLost?.();
            reject(new ApiError(401, "unauthorized", "Sitzung abgelaufen"));
          }
        });
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (xhr.status === 204 || !xhr.responseText) return resolve(undefined as T);
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch {
          resolve(undefined as T);
        }
      } else {
        reject(parseXhrError(xhr));
      }
    };
    xhr.onerror = () => {
      cleanup();
      reject(new ApiError(0, "network", "Netzwerkfehler beim Upload"));
    };
    xhr.send(form);
  });
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  del: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "DELETE",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

// Login/Logout/Refresh ausserhalb des Interceptors (setzen/loeschen das Token).
export async function loginRequest(email: string, password: string): Promise<string> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw await parseError(res);
  const data = (await res.json()) as { access_token: string };
  accessToken = data.access_token;
  return data.access_token;
}

export async function registerFirstAdminRequest(
  email: string,
  password: string,
  full_name: string,
): Promise<string> {
  const res = await fetch(`${BASE}/auth/register-first-admin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name }),
  });
  if (!res.ok) throw await parseError(res);
  const data = (await res.json()) as { access_token: string };
  accessToken = data.access_token;
  return data.access_token;
}

export async function bootstrapSession(): Promise<boolean> {
  return tryRefresh();
}

export async function logoutRequest(): Promise<void> {
  try {
    await rawRequest("/auth/logout", { method: "POST" });
  } finally {
    accessToken = null;
  }
}
