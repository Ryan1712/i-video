"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";

interface SceneInput {
  narration_text: string;
}

export default function NewEpisodePage() {
  return (
    <Suspense>
      <NewEpisodeInner />
    </Suspense>
  );
}

function NewEpisodeInner() {
  const t = useTranslations("episodes.new");
  const router = useRouter();
  const searchParams = useSearchParams();
  const [seriesList, setSeriesList] = useState<{ id: number; name: string }[]>([]);
  const [seriesId, setSeriesId] = useState<number | null>(
    searchParams.get("series") ? Number(searchParams.get("series")) : null
  );
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [scenes, setScenes] = useState<SceneInput[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get<{ id: number; name: string }[]>("/series").then(setSeriesList).catch(() => {});
  }, []);

  function addScene() {
    setScenes((prev) => [...prev, { narration_text: "" }]);
  }

  function removeScene(i: number) {
    setScenes((prev) => prev.filter((_, idx) => idx !== i));
  }

  function updateScene(i: number, text: string) {
    setScenes((prev) => prev.map((s, idx) => (idx === i ? { narration_text: text } : s)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (scenes.some((s) => !s.narration_text.trim())) {
      setError(t("narrationRequired"));
      return;
    }
    setError("");
    setLoading(true);
    try {
      const ep = await api.post<{ id: number }>("/episodes", {
        title,
        description,
        tags,
        series_id: seriesId,
        scenes: scenes.map((s) => ({ narration_text: s.narration_text })),
      });
      router.push(`/dashboard/episodes/${ep.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("createFailed"));
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    color: "#EDEDEF",
  };

  return (
    <div className="p-8 max-w-2xl mx-auto">
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
        {t("backToEpisodes")}
      </Link>

      <h1 className="text-2xl font-bold tracking-tight mb-1" style={{ color: "#EDEDEF" }}>
        {t("title")}
      </h1>
      <p className="text-sm mb-8" style={{ color: "#8A8F98" }}>
        {t("subtitle")}
      </p>

      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
        <select
          className="px-3 py-2 rounded-lg text-sm w-full mb-4"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#EDEDEF" }}
          value={seriesId ?? ""}
          onChange={(e) => setSeriesId(e.target.value ? Number(e.target.value) : null)}
          aria-label={t("seriesLabel")}
        >
          <option value="">{t("noSeries")}</option>
          {seriesList.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>

        {/* Title */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium" style={{ color: "#8A8F98" }}>{t("titleLabel")} *</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t("titlePlaceholder")}
            required
            className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all duration-200"
            style={inputStyle}
            onFocus={(e) => { e.currentTarget.style.border = "1px solid rgba(99,102,241,0.5)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.1)"; }}
            onBlur={(e) => { e.currentTarget.style.border = "1px solid rgba(255,255,255,0.1)"; e.currentTarget.style.boxShadow = "none"; }}
          />
        </div>

        {/* Description */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium" style={{ color: "#8A8F98" }}>{t("descriptionLabel")}</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t("descriptionPlaceholder")}
            rows={3}
            className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all duration-200 resize-none"
            style={inputStyle}
            onFocus={(e) => { e.currentTarget.style.border = "1px solid rgba(99,102,241,0.5)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.1)"; }}
            onBlur={(e) => { e.currentTarget.style.border = "1px solid rgba(255,255,255,0.1)"; e.currentTarget.style.boxShadow = "none"; }}
          />
        </div>

        {/* Tags */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium" style={{ color: "#8A8F98" }}>{t("tagsLabel")}</label>
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder={t("tagsPlaceholder")}
            className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all duration-200"
            style={inputStyle}
            onFocus={(e) => { e.currentTarget.style.border = "1px solid rgba(99,102,241,0.5)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.1)"; }}
            onBlur={(e) => { e.currentTarget.style.border = "1px solid rgba(255,255,255,0.1)"; e.currentTarget.style.boxShadow = "none"; }}
          />
        </div>

        {/* Scenes */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="text-xs font-medium" style={{ color: "#8A8F98" }}>
              {t("scenesCount", { count: scenes.length })}
            </label>
            <button
              type="button"
              onClick={addScene}
              className="flex items-center gap-1.5 text-xs font-medium transition-colors px-3 py-1.5 rounded-lg"
              style={{ color: "#818CF8", background: "rgba(99,102,241,0.1)" }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M6 2v8M2 6h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              {t("addScene")}
            </button>
          </div>
          <div className="flex flex-col gap-3">
            {scenes.map((scene, i) => (
              <div
                key={i}
                className="flex gap-3"
              >
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 mt-2.5"
                  style={{ background: "rgba(99,102,241,0.12)", color: "#818CF8" }}
                >
                  {i + 1}
                </div>
                <textarea
                  value={scene.narration_text}
                  onChange={(e) => updateScene(i, e.target.value)}
                  placeholder={t("narrationPlaceholder", { n: i + 1 })}
                  required
                  rows={2}
                  className="flex-1 px-4 py-2.5 rounded-xl text-sm outline-none transition-all duration-200 resize-none"
                  style={inputStyle}
                  onFocus={(e) => { e.currentTarget.style.border = "1px solid rgba(99,102,241,0.5)"; e.currentTarget.style.boxShadow = "0 0 0 3px rgba(99,102,241,0.1)"; }}
                  onBlur={(e) => { e.currentTarget.style.border = "1px solid rgba(255,255,255,0.1)"; e.currentTarget.style.boxShadow = "none"; }}
                />
                <button
                  type="button"
                  onClick={() => removeScene(i)}
                  className="flex-shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-2.5 transition-colors"
                  style={{ color: "#4A4F5A" }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(239,68,68,0.1)"; (e.currentTarget as HTMLElement).style.color = "#EF4444"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; (e.currentTarget as HTMLElement).style.color = "#4A4F5A"; }}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M2 10l8-8M10 10L2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <div className="px-4 py-3 rounded-xl text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#FCA5A5" }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 rounded-xl text-sm font-semibold text-white transition-all duration-200"
          style={{
            background: loading ? "rgba(99,102,241,0.5)" : "linear-gradient(135deg, #6366F1, #4F46E5)",
            boxShadow: loading ? "none" : "0 0 24px rgba(99,102,241,0.3)",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? t("creating") : t("create")}
        </button>
      </form>
    </div>
  );
}
