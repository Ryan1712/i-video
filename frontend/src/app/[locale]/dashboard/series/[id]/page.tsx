"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Link } from "@/i18n/navigation";
import { api, ApiError } from "@/lib/api";

interface Series {
  id: number;
  name: string;
  description: string;
  style: { language?: string; image_style_bible?: string; voice_id?: string };
  episode_count: number;
}

interface Asset {
  id: number;
  kind: string;
  name: string;
  description: string;
  object_key: string | null;
  source: string;
}

interface EpisodeListItem {
  id: number;
  title: string;
  status: string;
}

const panel = { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" };
const input = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#EDEDEF",
};

export default function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [series, setSeries] = useState<Series | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeListItem[]>([]);
  const [error, setError] = useState("");
  const [assetName, setAssetName] = useState("");
  const [assetKind, setAssetKind] = useState("character");
  const [assetDescription, setAssetDescription] = useState("");
  const [uploading, setUploading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, a, eps] = await Promise.all([
        api.get<Series>(`/series/${id}`),
        api.get<Asset[]>(`/series/${id}/assets`),
        api.get<EpisodeListItem[]>(`/episodes?series_id=${id}`),
      ]);
      setSeries(s);
      setAssets(a);
      setEpisodes(eps);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? "Series not found." : "Failed to load series.");
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleUpload(file: File) {
    if (!assetName.trim()) {
      setError("Asset name is required (the AI matches scenes to assets by name + description).");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const token = localStorage.getItem("access_token");
      const form = new FormData();
      form.append("file", file);
      form.append("kind", assetKind);
      form.append("name", assetName.trim());
      form.append("description", assetDescription);
      const res = await fetch(`/api/series/${id}/assets`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) throw new ApiError(res.status, "Upload failed");
      setAssetName("");
      setAssetDescription("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Asset upload failed.");
    } finally {
      setUploading(false);
    }
  }

  if (error && !series) return <div className="p-8"><p style={{ color: "#FCA5A5" }}>{error}</p></div>;
  if (!series) return <div className="p-8"><p style={{ color: "#8A8F98" }}>Loading…</p></div>;

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <Link href="/dashboard/series" className="text-sm mb-6 block w-fit" style={{ color: "#8A8F98" }}>
        ← All series
      </Link>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "#EDEDEF" }}>{series.name}</h1>
          {series.description && <p className="text-sm mt-1" style={{ color: "#8A8F98" }}>{series.description}</p>}
          <p className="text-xs mt-2" style={{ color: "#4A4F5A" }}>
            Language: {series.style.language ?? "en"}
            {series.style.image_style_bible ? ` · Style: ${series.style.image_style_bible}` : ""}
          </p>
        </div>
        <Link
          href={`/dashboard/episodes/new?series=${series.id}`}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white flex-shrink-0"
          style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}
        >
          New episode
        </Link>
      </div>

      <section className="mb-8">
        <h2 className="text-sm font-semibold mb-3" style={{ color: "#EDEDEF" }}>
          Shared assets ({assets.length})
        </h2>
        <div className="p-4 rounded-2xl mb-4 flex flex-col gap-3" style={panel}>
          <div className="flex gap-3">
            <input className="px-3 py-2 rounded-lg text-sm flex-1" style={input}
              placeholder="Asset name (e.g. main_character)" value={assetName}
              onChange={(e) => setAssetName(e.target.value)} />
            <select className="px-3 py-2 rounded-lg text-sm" style={input} value={assetKind}
              onChange={(e) => setAssetKind(e.target.value)} aria-label="Kind">
              <option value="character">character</option>
              <option value="location">location</option>
              <option value="object">object</option>
              <option value="other">other</option>
            </select>
          </div>
          <input className="px-3 py-2 rounded-lg text-sm" style={input}
            placeholder="Description — what is in this image (the AI matches scenes by this)"
            value={assetDescription} onChange={(e) => setAssetDescription(e.target.value)} />
          <label className="px-4 py-2 rounded-xl text-sm font-semibold text-white w-fit cursor-pointer"
            style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", opacity: uploading ? 0.6 : 1 }}>
            {uploading ? "Uploading…" : "Upload image"}
            <input type="file" accept="image/*" className="hidden" disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
                e.target.value = "";
              }} />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {assets.map((a) => (
            <div key={a.id} className="p-3 rounded-xl" style={panel}>
              <p className="text-sm font-medium" style={{ color: "#EDEDEF" }}>
                {a.name}
                <span className="text-xs ml-2 px-1.5 py-0.5 rounded" style={{
                  background: a.source === "generated" ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.06)",
                  color: a.source === "generated" ? "#818CF8" : "#8A8F98",
                }}>
                  {a.source === "generated" ? "AI" : a.kind}
                </span>
              </p>
              {a.description && <p className="text-xs mt-1" style={{ color: "#8A8F98" }}>{a.description}</p>}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold mb-3" style={{ color: "#EDEDEF" }}>Episodes</h2>
        <div className="flex flex-col gap-2">
          {episodes.map((ep) => (
            <Link key={ep.id} href={`/dashboard/episodes/${ep.id}`}
              className="p-3 rounded-xl flex items-center justify-between" style={panel}>
              <span className="text-sm" style={{ color: "#EDEDEF" }}>{ep.title}</span>
              <span className="text-xs" style={{ color: "#8A8F98" }}>{ep.status}</span>
            </Link>
          ))}
          {episodes.length === 0 && <p className="text-sm" style={{ color: "#8A8F98" }}>No episodes yet.</p>}
        </div>
      </section>

      {error && <p className="text-sm mt-4" style={{ color: "#FCA5A5" }}>{error}</p>}
    </div>
  );
}
