"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Link } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";
import ScriptPanel from "@/components/episode/ScriptPanel";

interface Scene {
  id: number;
  order_index: number;
  narration_text: string;
  asset_object_key: string | null;
  asset_brief: string | null;
}

interface Episode {
  id: number;
  title: string;
  description: string;
  tags: string;
  status: string;
  output_object_key: string | null;
  youtube_video_id: string | null;
  scenes: Scene[];
  brief: string;
  script: string;
  target_duration_sec: number | null;
  series_id: number | null;
}

interface Job {
  id: number;
  status: string;
  progress_pct: number;
  stage: string | null;
  error_message: string | null;
}

function stageLabel(stage: string | null): string {
  if (!stage) return "Working…";
  const [phase, count] = stage.split(" ");
  if (phase === "tts") return `Voice-over ${count ?? ""}`;
  if (phase === "render") return `Rendering scenes ${count ?? ""}`;
  if (phase === "assemble") return "Assembling final video…";
  return stage;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  draft:     { label: "Draft",     color: "#8A8F98", bg: "rgba(255,255,255,0.05)", border: "rgba(255,255,255,0.1)" },
  building:  { label: "Building…", color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.3)" },
  built:     { label: "Built",     color: "#10B981", bg: "rgba(16,185,129,0.1)",   border: "rgba(16,185,129,0.3)" },
  uploading: { label: "Uploading…",color: "#818CF8", bg: "rgba(99,102,241,0.1)",  border: "rgba(99,102,241,0.3)" },
  uploaded:  { label: "Published", color: "#10B981", bg: "rgba(16,185,129,0.1)",  border: "rgba(16,185,129,0.3)" },
};

const GENERATE_ASSET_ERRORS: Record<string, string> = {
  ERR_IMAGE_GENERATION_FAILED: "Image generation failed — try again or upload manually.",
  ERR_NO_SERIES: "This episode has no series — link it to a series to generate images.",
  ERR_NO_ASSET_BRIEF: "This scene has no missing-image description to generate from.",
};

export default function EpisodeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadingScene, setUploadingScene] = useState<number | null>(null);
  const [generatingScene, setGeneratingScene] = useState<number | null>(null);
  const [building, setBuilding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [jobError, setJobError] = useState("");
  const [outputUrl, setOutputUrl] = useState<string | null>(null);
  const [latestJob, setLatestJob] = useState<Job | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchEpisode = useCallback(async () => {
    try {
      const ep = await api.get<Episode>(`/episodes/${id}`);
      setEpisode(ep);

      try {
        setLatestJob(await api.get<Job>(`/episodes/${id}/jobs/latest`));
      } catch {} // 404 = no jobs yet

      if (ep.status === "built" && ep.output_object_key && !outputUrl) {
        try {
          const { url } = await api.get<{ url: string }>(`/episodes/${id}/output-url`);
          setOutputUrl(url);
        } catch {}
      }

      return ep.status;
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError("Episode not found.");
      } else {
        setError("Failed to load episode.");
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, [id, outputUrl]);

  useEffect(() => {
    fetchEpisode();
  }, [fetchEpisode]);

  // Poll while building or uploading
  useEffect(() => {
    if (!episode) return;
    const busy = episode.status === "building" || episode.status === "uploading";
    if (busy) {
      pollRef.current = setInterval(() => fetchEpisode(), 3000);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [episode?.status, fetchEpisode]);

  async function handleAssetUpload(scene: Scene, file: File) {
    setUploadingScene(scene.id);
    try {
      const token = localStorage.getItem("access_token");
      const form = new FormData();
      form.append("file", file);
      // Raw fetch (not the api helper) because FormData must set its own Content-Type.
      const res = await fetch(
        `/api/episodes/${id}/scenes/${scene.id}/asset`,
        { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: form },
      );
      if (!res.ok) throw new ApiError(res.status, "Upload failed");
      await fetchEpisode();
    } catch (err) {
      setJobError(err instanceof ApiError ? err.detail : "Asset upload failed.");
    } finally {
      setUploadingScene(null);
    }
  }

  async function handleGenerateAsset(scene: Scene) {
    setGeneratingScene(scene.id);
    setJobError("");
    try {
      await api.post(`/episodes/${id}/scenes/${scene.id}/generate-asset`, {});
      await fetchEpisode();
    } catch (err) {
      if (err instanceof ApiError) {
        setJobError(GENERATE_ASSET_ERRORS[err.detail] ?? err.detail);
      } else {
        setJobError("Image generation failed.");
      }
    } finally {
      setGeneratingScene(null);
    }
  }

  async function handleBuild() {
    if (
      episode &&
      (episode.status === "built" || episode.status === "uploaded") &&
      !window.confirm(
        "This episode is already built. Rebuilding re-runs voice-over for every scene and costs TTS credits. Continue?"
      )
    ) {
      return;
    }
    setJobError("");
    setBuilding(true);
    try {
      await api.post<Job>(`/episodes/${id}/build`, {});
      await fetchEpisode();
    } catch (err) {
      setJobError(err instanceof ApiError ? err.detail : "Failed to start build.");
    } finally {
      setBuilding(false);
    }
  }

  async function handleUploadYouTube() {
    setJobError("");
    setUploading(true);
    try {
      await api.post<Job>(`/episodes/${id}/upload`, {});
      await fetchEpisode();
    } catch (err) {
      if (err instanceof ApiError && err.detail === "ERR_YOUTUBE_NOT_CONNECTED") {
        setJobError("YouTube not connected. Go to YouTube settings first.");
      } else {
        setJobError(err instanceof ApiError ? err.detail : "Failed to start upload.");
      }
    } finally {
      setUploading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-96">
        <div className="w-6 h-6 rounded-full border-2 animate-spin" style={{ borderColor: "#6366F1", borderTopColor: "transparent" }} />
      </div>
    );
  }

  if (error || !episode) {
    return (
      <div className="p-8">
        <p style={{ color: "#FCA5A5" }}>{error || "Episode not found."}</p>
      </div>
    );
  }

  const cfg = STATUS_CONFIG[episode.status] ?? STATUS_CONFIG.draft;
  const allAssetsReady = episode.scenes.length > 0 && episode.scenes.every((s) => s.asset_object_key);
  const isBusy = episode.status === "building" || episode.status === "uploading";

  return (
    <div className="p-8 max-w-3xl mx-auto">
      {/* Back */}
      <Link
        href="/dashboard"
        className="flex items-center gap-2 text-sm mb-6 w-fit transition-colors"
        style={{ color: "#8A8F98" }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#EDEDEF")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "#8A8F98")}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M9 3L5 7l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        All episodes
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-8 gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold tracking-tight truncate" style={{ color: "#EDEDEF" }}>
            {episode.title}
          </h1>
          {episode.description && (
            <p className="text-sm mt-1 line-clamp-2" style={{ color: "#8A8F98" }}>
              {episode.description}
            </p>
          )}
          {episode.tags && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {episode.tags.split(",").filter(Boolean).map((tag) => (
                <span key={tag} className="text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(99,102,241,0.1)", color: "#818CF8", border: "1px solid rgba(99,102,241,0.2)" }}>
                  {tag.trim()}
                </span>
              ))}
            </div>
          )}
        </div>
        <span className="flex-shrink-0 text-xs font-medium px-3 py-1.5 rounded-full" style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}` }}>
          {cfg.label}
        </span>
      </div>

      {episode.status === "draft" && (
        <ScriptPanel
          episodeId={episode.id}
          initialBrief={episode.brief}
          initialDurationSec={episode.target_duration_sec}
          initialScript={episode.script}
          disabled={isBusy}
          onEpisodeUpdated={fetchEpisode}
        />
      )}

      {/* Scenes */}
      <section className="mb-8">
        <h2 className="text-sm font-semibold mb-3" style={{ color: "#EDEDEF" }}>
          Scenes — upload an asset image for each
        </h2>
        <div className="flex flex-col gap-3">
          {episode.scenes.map((scene) => (
            <div
              key={scene.id}
              className="flex gap-4 p-4 rounded-2xl"
              style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" }}
            >
              <div className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5" style={{ background: "rgba(99,102,241,0.12)", color: "#818CF8" }}>
                {scene.order_index + 1}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm mb-3" style={{ color: "#EDEDEF" }}>{scene.narration_text}</p>
                {!scene.asset_object_key && scene.asset_brief && (
                  <p className="text-xs mb-2 italic" style={{ color: "#8A8F98" }}>
                    Missing image: {scene.asset_brief}
                  </p>
                )}
                <div className="flex items-center gap-3">
                  {!scene.asset_object_key && scene.asset_brief && (
                    <button
                      onClick={() => handleGenerateAsset(scene)}
                      disabled={isBusy || generatingScene !== null}
                      className="flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-lg transition-all"
                      style={{
                        background: "rgba(99,102,241,0.12)",
                        border: "1px solid rgba(99,102,241,0.25)",
                        color: "#818CF8",
                        opacity: isBusy ? 0.5 : 1,
                      }}
                      title={scene.asset_brief}
                    >
                      {generatingScene === scene.id ? (
                        <div className="w-3 h-3 rounded-full border border-t-transparent animate-spin" style={{ borderColor: "#818CF8", borderTopColor: "transparent" }} />
                      ) : (
                        "✨"
                      )}
                      Generate image
                    </button>
                  )}
                  {scene.asset_object_key ? (
                    <span className="flex items-center gap-1.5 text-xs" style={{ color: "#10B981" }}>
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <circle cx="7" cy="7" r="6" fill="rgba(16,185,129,0.15)" stroke="#10B981" strokeWidth="1" />
                        <path d="M4.5 7l2 2 3-3" stroke="#10B981" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      Asset ready
                    </span>
                  ) : null}
                  <label
                    className="flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-lg cursor-pointer transition-all"
                    style={{
                      background: uploadingScene === scene.id ? "rgba(99,102,241,0.08)" : "rgba(255,255,255,0.06)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      color: "#8A8F98",
                      opacity: isBusy ? 0.5 : 1,
                      pointerEvents: isBusy ? "none" : "auto",
                    }}
                  >
                    {uploadingScene === scene.id ? (
                      <div className="w-3 h-3 rounded-full border border-t-transparent animate-spin" style={{ borderColor: "#818CF8", borderTopColor: "transparent" }} />
                    ) : (
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M6 8V2M3 5l3-3 3 3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                        <path d="M1 10h10" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                      </svg>
                    )}
                    {scene.asset_object_key ? "Replace asset" : "Upload asset"}
                    <input
                      type="file"
                      accept="image/*,video/*"
                      className="hidden"
                      disabled={isBusy || uploadingScene !== null}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleAssetUpload(scene, f);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Divider */}
      <div className="h-px mb-8" style={{ background: "rgba(255,255,255,0.06)" }} />

      {/* Build */}
      <section className="mb-8">
        <h2 className="text-sm font-semibold mb-1" style={{ color: "#EDEDEF" }}>Build video</h2>
        <p className="text-xs mb-4" style={{ color: "#8A8F98" }}>
          All scenes need an uploaded asset before building.
        </p>

        {episode.status === "building" && (
          <div className="mb-4">
            <div className="flex items-center justify-between text-xs mb-1.5" style={{ color: "#8A8F98" }}>
              <span>{stageLabel(latestJob?.stage ?? null)}</span>
              <span>{latestJob ? `${latestJob.progress_pct}%` : ""}</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.max(latestJob?.progress_pct ?? 0, 3)}%`,
                  background: "linear-gradient(90deg, #6366F1, #818CF8)",
                  animation: "shimmer 1.5s linear infinite",
                  backgroundSize: "200% 100%",
                }}
              />
            </div>
          </div>
        )}

        {latestJob?.status === "failed" && episode.status !== "building" && (
          <div
            className="mb-4 px-4 py-3 rounded-xl text-sm flex items-center justify-between gap-4"
            style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#FCA5A5" }}
          >
            <span>Last build failed: {latestJob.error_message || "unknown error"}</span>
            <button
              onClick={handleBuild}
              className="flex-shrink-0 text-xs font-semibold px-3 py-1.5 rounded-lg"
              style={{ background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.35)", color: "#FCA5A5" }}
            >
              Retry build
            </button>
          </div>
        )}

        {outputUrl && (episode.status === "built" || episode.status === "uploaded") && (
          <a
            href={outputUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-xs font-medium px-4 py-2 rounded-lg mb-4 transition-all"
            style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)", color: "#10B981" }}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M5 2H3a1 1 0 00-1 1v6a1 1 0 001 1h6a1 1 0 001-1V7M7 2h3v3M10 2L5.5 6.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Download output video
          </a>
        )}

        <button
          onClick={handleBuild}
          disabled={!allAssetsReady || isBusy || building}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200"
          style={{
            background: allAssetsReady && !isBusy
              ? "linear-gradient(135deg, #6366F1, #4F46E5)"
              : "rgba(99,102,241,0.25)",
            boxShadow: allAssetsReady && !isBusy ? "0 0 20px rgba(99,102,241,0.3)" : "none",
            cursor: allAssetsReady && !isBusy ? "pointer" : "not-allowed",
            opacity: isBusy ? 0.6 : 1,
          }}
        >
          {building ? (
            <div className="w-4 h-4 rounded-full border-2 animate-spin" style={{ borderColor: "white", borderTopColor: "transparent" }} />
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 7c0-2.76 2.24-5 5-5s5 2.24 5 5-2.24 5-5 5-5-2.24-5-5z" stroke="currentColor" strokeWidth="1.2" />
              <path d="M6 5l3 2-3 2V5z" fill="currentColor" />
            </svg>
          )}
          {episode.status === "building" ? "Building…" : "Build episode"}
        </button>
        {!allAssetsReady && (
          <p className="text-xs mt-2" style={{ color: "#4A4F5A" }}>
            Upload assets for all {episode.scenes.length} scenes to enable build.
          </p>
        )}
      </section>

      {/* YouTube publish */}
      {(episode.status === "built" || episode.status === "uploaded") && (
        <>
          <div className="h-px mb-8" style={{ background: "rgba(255,255,255,0.06)" }} />
          <section>
            <h2 className="text-sm font-semibold mb-1" style={{ color: "#EDEDEF" }}>Publish to YouTube</h2>
            <p className="text-xs mb-4" style={{ color: "#8A8F98" }}>
              {episode.status === "uploaded"
                ? "Episode published to YouTube."
                : "Upload the built video directly to your connected YouTube channel."}
            </p>

            {episode.status === "uploading" && (
              <div className="mb-4">
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.08)" }}>
                  <div className="h-full rounded-full" style={{ width: "60%", background: "linear-gradient(90deg, #818CF8, #6366F1)", animation: "shimmer 1.5s linear infinite", backgroundSize: "200% 100%" }} />
                </div>
              </div>
            )}

            {episode.youtube_video_id && (
              <a
                href={`https://youtu.be/${episode.youtube_video_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-xs font-medium px-4 py-2 rounded-lg mb-4 transition-all"
                style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#FCA5A5" }}
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                  <path d="M11.5 3.5s-.15-1-.6-1.4c-.57-.6-1.2-.6-1.5-.6C7.9 1.4 6 1.4 6 1.4s-1.9 0-3.4.1c-.3 0-.93 0-1.5.6-.45.4-.6 1.4-.6 1.4S.4 4.7.4 6v.9c0 1.1.1 2.1.1 2.1s.15 1 .6 1.4c.57.6 1.33.55 1.67.6C3.9 11 6 11 6 11s1.9 0 3.4-.1c.3 0 .93 0 1.5-.6.45-.4.6-1.4.6-1.4s.1-1 .1-2.1V6c0-1.3-.1-2.5-.1-2.5zM4.87 7.9V4.37L8 6.13 4.87 7.9z" />
                </svg>
                View on YouTube
              </a>
            )}

            {episode.status !== "uploaded" && (
              <button
                onClick={handleUploadYouTube}
                disabled={uploading || episode.status === "uploading"}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white transition-all duration-200"
                style={{
                  background: episode.status === "uploading" || uploading
                    ? "rgba(99,102,241,0.25)"
                    : "linear-gradient(135deg, #EF4444, #DC2626)",
                  boxShadow: episode.status === "uploading" || uploading ? "none" : "0 0 20px rgba(239,68,68,0.25)",
                  cursor: episode.status === "uploading" || uploading ? "not-allowed" : "pointer",
                }}
              >
                {uploading ? (
                  <div className="w-4 h-4 rounded-full border-2 animate-spin" style={{ borderColor: "white", borderTopColor: "transparent" }} />
                ) : (
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                    <path d="M13 3.7s-.17-1.2-.7-1.7c-.67-.7-1.4-.7-1.73-.7C8.9 1.2 7 1.2 7 1.2s-1.9 0-3.57.1c-.33 0-1.06 0-1.73.7-.53.5-.7 1.7-.7 1.7S.8 5.1.8 6.4V7.5c0 1.3.2 2.6.2 2.6s.17 1.2.7 1.7c.67.7 1.53.65 1.93.7C4.9 12.6 7 12.6 7 12.6s1.9 0 3.57-.1c.33 0 1.06 0 1.73-.7.53-.5.7-1.7.7-1.7s.2-1.3.2-2.6V6.4c0-1.3-.2-2.7-.2-2.7zM5.6 9.3V5.1l4.7 2.1-4.7 2.1z" />
                  </svg>
                )}
                {episode.status === "uploading" ? "Uploading…" : "Publish to YouTube"}
              </button>
            )}
          </section>
        </>
      )}

      {/* Job error */}
      {jobError && (
        <div className="mt-6 px-4 py-3 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#FCA5A5" }}>
          {jobError}
        </div>
      )}
    </div>
  );
}
