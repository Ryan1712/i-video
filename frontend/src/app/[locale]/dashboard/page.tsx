"use client";

import { useEffect, useState } from "react";
import { Link } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";

interface Episode {
  id: number;
  title: string;
  description: string;
  status: string;
  youtube_video_id: string | null;
  output_object_key: string | null;
  scenes: { id: number }[];
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  draft:     { label: "Draft",     color: "#8A8F98", bg: "rgba(255,255,255,0.05)", border: "rgba(255,255,255,0.1)" },
  building:  { label: "Building",  color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)" },
  built:     { label: "Built",     color: "#10B981", bg: "rgba(16,185,129,0.1)",   border: "rgba(16,185,129,0.25)" },
  uploading: { label: "Uploading", color: "#818CF8", bg: "rgba(99,102,241,0.1)",  border: "rgba(99,102,241,0.25)" },
  uploaded:  { label: "Published", color: "#10B981", bg: "rgba(16,185,129,0.1)",  border: "rgba(16,185,129,0.25)" },
};

export default function DashboardPage() {
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<Episode[]>("/episodes")
      .then(setEpisodes)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = "/login";
        } else {
          setError("Failed to load episodes.");
        }
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "#EDEDEF" }}>
            Episodes
          </h1>
          <p className="text-sm mt-1" style={{ color: "#8A8F98" }}>
            {episodes.length} episode{episodes.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/dashboard/episodes/new"
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200"
          style={{
            background: "linear-gradient(135deg, #6366F1, #4F46E5)",
            boxShadow: "0 0 20px rgba(99,102,241,0.3)",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.boxShadow = "0 0 30px rgba(99,102,241,0.5)";
            (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.boxShadow = "0 0 20px rgba(99,102,241,0.3)";
            (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          New episode
        </Link>
      </div>

      {/* Content */}
      {loading && (
        <div className="flex items-center justify-center py-24">
          <div
            className="w-6 h-6 rounded-full border-2 animate-spin"
            style={{ borderColor: "#6366F1", borderTopColor: "transparent" }}
          />
        </div>
      )}

      {error && (
        <div
          className="px-4 py-3 rounded-xl text-sm"
          style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#FCA5A5" }}
        >
          {error}
        </div>
      )}

      {!loading && !error && episodes.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
            style={{ background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.2)" }}
          >
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
              <path
                d="M14 6v16M6 14h16"
                stroke="#6366F1"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <h3 className="text-base font-semibold mb-2" style={{ color: "#EDEDEF" }}>
            No episodes yet
          </h3>
          <p className="text-sm mb-6" style={{ color: "#8A8F98" }}>
            Create your first What If episode to get started.
          </p>
          <Link
            href="/dashboard/episodes/new"
            className="px-5 py-2.5 rounded-xl text-sm font-semibold text-white"
            style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}
          >
            Create episode
          </Link>
        </div>
      )}

      {!loading && episodes.length > 0 && (
        <div className="flex flex-col gap-3">
          {episodes.map((ep) => {
            const cfg = STATUS_CONFIG[ep.status] ?? STATUS_CONFIG.draft;
            return (
              <Link
                key={ep.id}
                href={`/dashboard/episodes/${ep.id}`}
                className="flex items-center gap-4 p-5 rounded-2xl transition-all duration-200 group"
                style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.055)";
                  (e.currentTarget as HTMLElement).style.borderColor = "rgba(255,255,255,0.1)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.03)";
                  (e.currentTarget as HTMLElement).style.borderColor = "rgba(255,255,255,0.07)";
                }}
              >
                {/* Episode number */}
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0"
                  style={{ background: "rgba(99,102,241,0.12)", color: "#818CF8" }}
                >
                  {ep.id}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm truncate" style={{ color: "#EDEDEF" }}>
                    {ep.title}
                  </p>
                  <p className="text-xs mt-0.5 truncate" style={{ color: "#4A4F5A" }}>
                    {ep.scenes.length} scene{ep.scenes.length !== 1 ? "s" : ""}
                    {ep.youtube_video_id && " · YouTube"}
                  </p>
                </div>

                {/* Status badge */}
                <span
                  className="flex-shrink-0 text-xs font-medium px-2.5 py-1 rounded-full"
                  style={{
                    background: cfg.bg,
                    color: cfg.color,
                    border: `1px solid ${cfg.border}`,
                  }}
                >
                  {cfg.label}
                </span>

                {/* Arrow */}
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <path
                    d="M6 4l4 4-4 4"
                    stroke="#8A8F98"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
