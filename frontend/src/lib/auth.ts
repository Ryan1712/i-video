import { api } from "./api";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function saveToken(token: string) {
  localStorage.setItem("access_token", token);
}

export function clearToken() {
  localStorage.removeItem("access_token");
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export async function login(email: string, password: string): Promise<void> {
  const res = await api.post<TokenResponse>("/auth/login", { email, password });
  saveToken(res.access_token);
}

export async function signup(email: string, password: string): Promise<void> {
  await api.post("/auth/signup", { email, password });
  await login(email, password);
}

export function logout() {
  clearToken();
  // Middleware rewrites this to /<defaultLocale>/login; acceptable to lose
  // the active locale on logout (Wave 2 may read the cookie instead).
  window.location.href = "/login";
}
