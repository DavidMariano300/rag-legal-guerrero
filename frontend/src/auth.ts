const TOKEN_KEY = "rag_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

async function authRequest(path: string, email: string, password: string): Promise<string> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Error (${res.status})`);
  }

  const data: TokenResponse = await res.json();
  setToken(data.access_token);
  return data.access_token;
}

export async function entrarComoInvitado(): Promise<void> {
  const res = await fetch("/api/auth/invitado", { method: "POST" });
  if (!res.ok) {
    throw new Error(res.status === 404 ? "El acceso como invitado no está disponible." : `Error (${res.status})`);
  }
  const data: TokenResponse = await res.json();
  setToken(data.access_token);
}

export function login(email: string, password: string): Promise<string> {
  return authRequest("/api/auth/login", email, password);
}

export function register(email: string, password: string): Promise<string> {
  return authRequest("/api/auth/register", email, password);
}

/** fetch con el header de autorización agregado; limpia el token si el servidor responde 401. */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(input, { ...init, headers });
  if (res.status === 401) {
    clearToken();
  }
  return res;
}
