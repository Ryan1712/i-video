"use client";

import { useState } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { login } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Invalid email or password." : err.detail);
      } else {
        setError("Something went wrong. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md">
      {/* Ambient glow */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[400px] rounded-full pointer-events-none"
        style={{
          background: "radial-gradient(ellipse, rgba(99,102,241,0.1) 0%, transparent 70%)",
          filter: "blur(60px)",
        }}
      />

      <div className="relative">
        <h1
          className="text-2xl font-bold tracking-tight mb-1"
          style={{ color: "#EDEDEF" }}
        >
          Welcome back
        </h1>
        <p className="text-sm mb-8" style={{ color: "#8A8F98" }}>
          Sign in to continue making videos
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium" style={{ color: "#8A8F98" }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
              className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all duration-200"
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "#EDEDEF",
              }}
              onFocus={(e) => {
                e.currentTarget.style.border = "1px solid rgba(99,102,241,0.5)";
                e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.12)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.border = "1px solid rgba(255,255,255,0.1)";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium" style={{ color: "#8A8F98" }}>
                Password
              </label>
              <a
                href="#"
                className="text-xs transition-colors"
                style={{ color: "#6366F1" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "#818CF8")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "#6366F1")}
              >
                Forgot password?
              </a>
            </div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              autoComplete="current-password"
              className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all duration-200"
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "#EDEDEF",
              }}
              onFocus={(e) => {
                e.currentTarget.style.border = "1px solid rgba(99,102,241,0.5)";
                e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.12)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.border = "1px solid rgba(255,255,255,0.1)";
                e.currentTarget.style.boxShadow = "none";
              }}
            />
          </div>

          {error && (
            <div
              className="px-4 py-3 rounded-xl text-sm"
              style={{
                background: "rgba(239,68,68,0.1)",
                border: "1px solid rgba(239,68,68,0.25)",
                color: "#FCA5A5",
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl text-sm font-semibold text-white transition-all duration-200 mt-1"
            style={{
              background: loading
                ? "rgba(99,102,241,0.5)"
                : "linear-gradient(135deg, #6366F1, #4F46E5)",
              boxShadow: loading ? "none" : "0 0 24px rgba(99,102,241,0.3)",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-center text-sm mt-6" style={{ color: "#8A8F98" }}>
          Don&apos;t have an account?{" "}
          <Link
            href="/signup"
            className="font-medium transition-colors"
            style={{ color: "#818CF8" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#6366F1")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "#818CF8")}
          >
            Sign up free
          </Link>
        </p>
      </div>
    </div>
  );
}
