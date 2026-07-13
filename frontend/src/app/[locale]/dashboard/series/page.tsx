"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";

interface Series {
  id: number;
  name: string;
  description: string;
  style: Record<string, unknown>;
  episode_count: number;
}

const panel = { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" };
const input = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#EDEDEF",
};

export default function SeriesPage() {
  const t = useTranslations("series");
  const [series, setSeries] = useState<Series[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("en");
  const [styleBible, setStyleBible] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function refresh() {
    try {
      setSeries(await api.get<Series[]>("/series"));
    } catch {
      setError(t("loadError"));
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate() {
    if (!name.trim()) {
      setError(t("nameRequired"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.post<Series>("/series", {
        name: name.trim(),
        description,
        style: { language, image_style_bible: styleBible, voice_id: voiceId.trim() },
      });
      setShowForm(false);
      setName("");
      setDescription("");
      setStyleBible("");
      setVoiceId("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("createFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold" style={{ color: "#EDEDEF" }}>{t("title")}</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white"
          style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}
        >
          {t("new")}
        </button>
      </div>

      {showForm && (
        <div className="p-4 rounded-2xl mb-6 flex flex-col gap-3" style={panel}>
          <input className="px-3 py-2 rounded-lg text-sm" style={input}
            placeholder={t("namePlaceholder")} value={name} onChange={(e) => setName(e.target.value)} />
          <textarea className="px-3 py-2 rounded-lg text-sm" style={input} rows={2}
            placeholder={t("descriptionPlaceholder")} value={description} onChange={(e) => setDescription(e.target.value)} />
          <select className="px-3 py-2 rounded-lg text-sm w-40" style={input}
            value={language} onChange={(e) => setLanguage(e.target.value)} aria-label={t("language")}>
            <option value="en">English</option>
            <option value="vi">Tiếng Việt</option>
          </select>
          <textarea className="px-3 py-2 rounded-lg text-sm" style={input} rows={3}
            placeholder={t("styleBiblePlaceholder")}
            value={styleBible} onChange={(e) => setStyleBible(e.target.value)} />
          <input className="px-3 py-2 rounded-lg text-sm" style={input}
            placeholder={t("voicePlaceholder")}
            value={voiceId} onChange={(e) => setVoiceId(e.target.value)} />
          <button
            onClick={handleCreate}
            disabled={saving}
            className="px-4 py-2 rounded-xl text-sm font-semibold text-white w-fit"
            style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", opacity: saving ? 0.6 : 1 }}
          >
            {t("create")}
          </button>
        </div>
      )}

      {error && <p className="text-sm mb-4" style={{ color: "#FCA5A5" }}>{error}</p>}

      <div className="flex flex-col gap-3">
        {series.map((s) => (
          <Link key={s.id} href={`/dashboard/series/${s.id}`}
            className="p-4 rounded-2xl flex items-center justify-between" style={panel}>
            <div>
              <p className="text-sm font-semibold" style={{ color: "#EDEDEF" }}>{s.name}</p>
              {s.description && <p className="text-xs mt-1" style={{ color: "#8A8F98" }}>{s.description}</p>}
            </div>
            <span className="text-xs" style={{ color: "#8A8F98" }}>{t("episodeCount", { count: s.episode_count })}</span>
          </Link>
        ))}
        {series.length === 0 && !showForm && (
          <p className="text-sm" style={{ color: "#8A8F98" }}>
            {t("empty")}
          </p>
        )}
      </div>
    </div>
  );
}
