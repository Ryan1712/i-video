"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

interface YouTubeStatus {
  connected: boolean;
  channel_id: string | null;
  channel_title: string | null;
}

export default function YouTubePage() {
  const [status, setStatus] = useState<YouTubeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<YouTubeStatus>("/youtube/status")
      .then(setStatus)
      .catch(() => setError("Failed to load YouTube status."))
      .finally(() => setLoading(false));
  }, []);

  async function handleConnect() {
    setError("");
    setConnecting(true);
    try {
      const { url } = await api.get<{ url: string }>("/youtube/connect");
      window.location.href = url;
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to start YouTube connection.");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    if (!confirm("Disconnect your YouTube channel?")) return;
    setError("");
    setDisconnecting(true);
    try {
      await api.delete("/youtube/disconnect");
      setStatus({ connected: false, channel_id: null, channel_title: null });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to disconnect.");
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold tracking-tight mb-1" style={{ color: "#EDEDEF" }}>
        YouTube
      </h1>
      <p className="text-sm mb-8" style={{ color: "#8A8F98" }}>
        Connect your YouTube channel to publish episodes automatically.
      </p>

      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="w-5 h-5 rounded-full border-2 animate-spin" style={{ borderColor: "#6366F1", borderTopColor: "transparent" }} />
        </div>
      )}

      {!loading && status && (
        <div
          className="p-6 rounded-2xl"
          style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
        >
          {status.connected ? (
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                {/* YouTube icon */}
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.2)" }}
                >
                  <svg width="22" height="22" viewBox="0 0 22 22" fill="#EF4444">
                    <path d="M20.5 6.5s-.28-2-.93-2.7c-.88-.93-1.87-.93-2.32-.93C14.55 2.7 11 2.7 11 2.7s-3.55 0-6.25.17c-.45 0-1.44 0-2.32.93-.65.7-.93 2.7-.93 2.7S1.27 8.77 1.27 11v1.83c0 2.23.23 4.5.23 4.5s.28 2 .93 2.7c.88.93 2.04.9 2.56.97C6.6 21.2 11 21.2 11 21.2s3.55 0 6.25-.22c.45 0 1.44 0 2.32-.93.65-.7.93-2.7.93-2.7s.23-2.27.23-4.5V11c0-2.23-.23-4.5-.23-4.5zM8.77 14.48V8.03L14.87 11l-6.1 3.48z" />
                  </svg>
                </div>
                <div>
                  <p className="font-semibold text-sm" style={{ color: "#EDEDEF" }}>
                    {status.channel_title}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: "#8A8F98" }}>
                    {status.channel_id}
                  </p>
                  <div className="flex items-center gap-1.5 mt-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-400" style={{ boxShadow: "0 0 6px #10B981" }} />
                    <span className="text-xs" style={{ color: "#10B981" }}>Connected</span>
                  </div>
                </div>
              </div>
              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="flex-shrink-0 px-4 py-2 rounded-xl text-xs font-medium transition-all"
                style={{
                  background: "rgba(239,68,68,0.08)",
                  border: "1px solid rgba(239,68,68,0.2)",
                  color: "#FCA5A5",
                  cursor: disconnecting ? "not-allowed" : "pointer",
                  opacity: disconnecting ? 0.6 : 1,
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(239,68,68,0.15)"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(239,68,68,0.08)"; }}
              >
                {disconnecting ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center py-8 text-center">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.2)" }}
              >
                <svg width="28" height="28" viewBox="0 0 28 28" fill="#EF4444">
                  <path d="M26 8.5s-.35-2.5-1.43-3.58c-1.36-1.43-2.88-1.43-3.57-1.43C17.3 3.3 14 3.3 14 3.3s-3.3 0-7 .22c-.7 0-2.22 0-3.57 1.43C2.35 6 2 8.5 2 8.5S1.65 11.4 1.65 14.3v2.4C1.65 19.6 2 22.5 2 22.5s.35 2.5 1.43 3.57c1.35 1.43 3.13 1.38 3.93 1.5C10 27.8 14 27.8 14 27.8s3.3 0 7-.28c.7 0 2.22 0 3.57-1.43C25.65 25 26 22.5 26 22.5s.35-2.9.35-5.8v-2.4C26.35 11.4 26 8.5 26 8.5zM11.32 18.96V10.4L18.95 14l-7.63 4.96z" />
                </svg>
              </div>
              <h3 className="text-base font-semibold mb-2" style={{ color: "#EDEDEF" }}>
                Connect your YouTube channel
              </h3>
              <p className="text-sm mb-6 max-w-xs" style={{ color: "#8A8F98" }}>
                Publish episodes directly to YouTube with one click. You&apos;ll be redirected to Google to authorize access.
              </p>
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold text-white transition-all"
                style={{
                  background: connecting ? "rgba(239,68,68,0.4)" : "linear-gradient(135deg, #EF4444, #DC2626)",
                  boxShadow: connecting ? "none" : "0 0 24px rgba(239,68,68,0.25)",
                  cursor: connecting ? "not-allowed" : "pointer",
                }}
              >
                {connecting ? (
                  <div className="w-4 h-4 rounded-full border-2 animate-spin" style={{ borderColor: "white", borderTopColor: "transparent" }} />
                ) : (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M14.8 4.5s-.2-1.4-.82-2.05C13.2.75 12.42.75 12.07.75 10.1.6 8 .6 8 .6s-2.1 0-4.07.15c-.35 0-1.13 0-1.91.82C1.4 2.12 1.2 3.5 1.2 3.5S1 5.1 1 6.7v1.3c0 1.6.2 3.2.2 3.2s.2 1.4.82 2.05c.78.77 1.8.74 2.25.83C5.6 14.2 8 14.2 8 14.2s2.1 0 4.07-.17c.35 0 1.13 0 1.91-.83.62-.62.82-2.05.82-2.05s.2-1.6.2-3.2V6.7c0-1.6-.2-3.2-.2-3.2zM6.5 10.3V5.7L10.3 8 6.5 10.3z" />
                  </svg>
                )}
                {connecting ? "Redirecting to Google…" : "Connect YouTube"}
              </button>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="mt-4 px-4 py-3 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#FCA5A5" }}>
          {error}
        </div>
      )}

      {/* Info box */}
      <div
        className="mt-6 p-4 rounded-xl flex gap-3"
        style={{ background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.15)" }}
      >
        <svg className="flex-shrink-0 mt-0.5" width="14" height="14" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="7" r="6" stroke="#818CF8" strokeWidth="1" />
          <path d="M7 6v4M7 4.5v.5" stroke="#818CF8" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
        <p className="text-xs leading-relaxed" style={{ color: "#818CF8" }}>
          Narro requests upload-only access to your YouTube account. We never read your existing videos or access your account data.
        </p>
      </div>
    </div>
  );
}
