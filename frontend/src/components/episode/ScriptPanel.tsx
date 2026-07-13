"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";

interface Props {
  episodeId: number;
  initialBrief: string;
  initialDurationSec: number | null;
  initialScript: string;
  disabled: boolean;
  onEpisodeUpdated: () => void;
}

const panel = { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" };
const input = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#EDEDEF",
};

export default function ScriptPanel({
  episodeId,
  initialBrief,
  initialDurationSec,
  initialScript,
  disabled,
  onEpisodeUpdated,
}: Props) {
  const t = useTranslations("episodes.script");
  const te = useTranslations("errors");
  const [brief, setBrief] = useState(initialBrief);
  const [minutes, setMinutes] = useState<number | "">(
    initialDurationSec ? Math.round(initialDurationSec / 60) : 8
  );
  const [script, setScript] = useState(initialScript);
  const [generating, setGenerating] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  // Missing catalog keys resolve to their own dotted path in the Jest mock,
  // so comparing against that path is how we detect an unmapped ERR_ code.
  function friendlyError(err: unknown): string {
    if (err instanceof ApiError) {
      const path = `errors.${err.detail}`;
      const msg = te(err.detail);
      return msg === path ? err.detail : msg;
    }
    return te("generic");
  }

  async function handleGenerate() {
    if (!brief.trim()) {
      setError(t("briefRequired"));
      return;
    }
    setGenerating(true);
    setError("");
    try {
      const resolvedMinutes = minutes === "" ? 8 : minutes;
      const { script: generated } = await api.post<{ script: string }>(
        `/episodes/${episodeId}/generate-script`,
        { brief: brief.trim(), target_duration_sec: resolvedMinutes * 60 }
      );
      setScript(generated);
      onEpisodeUpdated();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setGenerating(false);
    }
  }

  async function handleAnalyze() {
    if (!script.trim()) {
      setError(t("scriptRequired"));
      return;
    }
    setAnalyzing(true);
    setError("");
    try {
      await api.post(`/episodes/${episodeId}/analyze-script`, { script: script.trim() });
      onEpisodeUpdated();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setAnalyzing(false);
    }
  }

  const busy = disabled || generating || analyzing;

  return (
    <section className="mb-8 p-4 rounded-2xl flex flex-col gap-3" style={panel}>
      <h2 className="text-sm font-semibold" style={{ color: "#EDEDEF" }}>{t("title")}</h2>

      <textarea
        className="px-3 py-2 rounded-lg text-sm"
        style={input}
        rows={2}
        placeholder={t("briefPlaceholder")}
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        disabled={busy}
      />
      <div className="flex items-center gap-3">
        <label className="text-xs" style={{ color: "#8A8F98" }} htmlFor="duration-minutes">
          {t("targetMinutes")}
        </label>
        <input
          id="duration-minutes"
          aria-label={t("targetMinutes")}
          type="number"
          min={1}
          max={60}
          className="px-3 py-2 rounded-lg text-sm w-20"
          style={input}
          value={minutes}
          onChange={(e) => {
            const v = e.target.value;
            setMinutes(v === "" ? "" : Number(v) || 1);
          }}
          disabled={busy}
        />
        <button
          onClick={handleGenerate}
          disabled={busy}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white"
          style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", opacity: busy ? 0.6 : 1 }}
        >
          {generating ? t("generating") : t("generate")}
        </button>
      </div>

      <textarea
        className="px-3 py-2 rounded-lg text-sm font-mono"
        style={input}
        rows={10}
        placeholder={t("scriptPlaceholder")}
        value={script}
        onChange={(e) => setScript(e.target.value)}
        disabled={busy}
      />
      <button
        onClick={handleAnalyze}
        disabled={busy || !script.trim()}
        className="px-4 py-2 rounded-xl text-sm font-semibold text-white w-fit"
        style={{
          background: script.trim() ? "linear-gradient(135deg, #10B981, #059669)" : "rgba(16,185,129,0.25)",
          opacity: busy ? 0.6 : 1,
        }}
      >
        {analyzing ? t("splitting") : t("split")}
      </button>
      <p className="text-xs" style={{ color: "#4A4F5A" }}>
        {t("splitHint")}
      </p>

      {error && <p className="text-sm" style={{ color: "#FCA5A5" }}>{error}</p>}
    </section>
  );
}
