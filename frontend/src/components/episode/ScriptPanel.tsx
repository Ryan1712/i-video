"use client";

import { useState } from "react";
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

const ERROR_MESSAGES: Record<string, string> = {
  ERR_SCRIPT_GENERATION_FAILED: "Script generation failed — please try again.",
  ERR_SCRIPT_ANALYSIS_FAILED: "Scene analysis failed — please try again.",
  ERR_EPISODE_NOT_DRAFT: "Scenes can only be regenerated while the episode is a draft.",
};

export default function ScriptPanel({
  episodeId,
  initialBrief,
  initialDurationSec,
  initialScript,
  disabled,
  onEpisodeUpdated,
}: Props) {
  const [brief, setBrief] = useState(initialBrief);
  const [minutes, setMinutes] = useState<number | "">(
    initialDurationSec ? Math.round(initialDurationSec / 60) : 8
  );
  const [script, setScript] = useState(initialScript);
  const [generating, setGenerating] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  function friendly(err: unknown, fallback: string) {
    if (err instanceof ApiError) return ERROR_MESSAGES[err.detail] ?? err.detail;
    return fallback;
  }

  async function handleGenerate() {
    if (!brief.trim()) {
      setError("Enter an episode idea first.");
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
      setError(friendly(err, "Script generation failed."));
    } finally {
      setGenerating(false);
    }
  }

  async function handleAnalyze() {
    if (!script.trim()) {
      setError("Write or generate a script first.");
      return;
    }
    setAnalyzing(true);
    setError("");
    try {
      await api.post(`/episodes/${episodeId}/analyze-script`, { script: script.trim() });
      onEpisodeUpdated();
    } catch (err) {
      setError(friendly(err, "Scene analysis failed."));
    } finally {
      setAnalyzing(false);
    }
  }

  const busy = disabled || generating || analyzing;

  return (
    <section className="mb-8 p-4 rounded-2xl flex flex-col gap-3" style={panel}>
      <h2 className="text-sm font-semibold" style={{ color: "#EDEDEF" }}>Script</h2>

      <textarea
        className="px-3 py-2 rounded-lg text-sm"
        style={input}
        rows={2}
        placeholder="Episode idea / brief — a rough idea or a partial script"
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        disabled={busy}
      />
      <div className="flex items-center gap-3">
        <label className="text-xs" style={{ color: "#8A8F98" }} htmlFor="duration-minutes">
          Target minutes
        </label>
        <input
          id="duration-minutes"
          aria-label="Target minutes"
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
          {generating ? "Generating…" : "Generate script"}
        </button>
      </div>

      <textarea
        className="px-3 py-2 rounded-lg text-sm font-mono"
        style={input}
        rows={10}
        placeholder="The full narration script appears here — edit freely before splitting into scenes. You can also paste a finished script directly."
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
        {analyzing ? "Splitting…" : "Split into scenes"}
      </button>
      <p className="text-xs" style={{ color: "#4A4F5A" }}>
        Splitting replaces the current scene list and matches each scene to your series assets.
      </p>

      {error && <p className="text-sm" style={{ color: "#FCA5A5" }}>{error}</p>}
    </section>
  );
}
