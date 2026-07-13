"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { api, ApiError } from "@/lib/api";

interface Subscription {
  plan_id: number;
  status: string;
  current_period_end: string | null;
}

const PLAN_KEYS = ["creator", "studio"] as const;
const FEATURE_COUNTS: Record<(typeof PLAN_KEYS)[number], number> = {
  creator: 4,
  studio: 4,
};
const HIGHLIGHT: Record<(typeof PLAN_KEYS)[number], boolean> = {
  creator: true,
  studio: false,
};

export default function BillingPage() {
  const t = useTranslations("billing");
  const tc = useTranslations("common");
  const [sub, setSub] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [noSub, setNoSub] = useState(false);

  useEffect(() => {
    api
      .get<Subscription>("/billing/subscription")
      .then(setSub)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setNoSub(true);
      })
      .finally(() => setLoading(false));
  }, []);

  const STATUS_LABELS: Record<string, { label: string; color: string; bg: string; border: string }> = {
    trialing: { label: t("status.trialing"), color: "#818CF8", bg: "rgba(99,102,241,0.1)",  border: "rgba(99,102,241,0.25)" },
    active:   { label: t("status.active"),   color: "#10B981", bg: "rgba(16,185,129,0.1)",  border: "rgba(16,185,129,0.25)" },
    past_due: { label: t("status.pastDue"),  color: "#F59E0B", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.25)" },
    canceled: { label: t("status.canceled"), color: "#8A8F98", bg: "rgba(255,255,255,0.05)", border: "rgba(255,255,255,0.1)" },
  };

  const plans = PLAN_KEYS.map((key) => ({
    key,
    name: t(`plans.${key}.name`),
    price: t(`plans.${key}.price`),
    features: Array.from({ length: FEATURE_COUNTS[key] }, (_, i) => t(`plans.${key}.features.${i}`)),
    highlight: HIGHLIGHT[key],
  }));

  const statusCfg = sub ? (STATUS_LABELS[sub.status] ?? STATUS_LABELS.canceled) : null;

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold tracking-tight mb-1" style={{ color: "#EDEDEF" }}>
        {t("title")}
      </h1>
      <p className="text-sm mb-8" style={{ color: "#8A8F98" }}>
        {t("subtitle")}
      </p>

      {/* Current plan */}
      <div
        className="p-6 rounded-2xl mb-8"
        style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
      >
        <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "#4A4F5A" }}>
          {t("currentPlan")}
        </p>

        {loading && (
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded-full border-2 animate-spin" style={{ borderColor: "#6366F1", borderTopColor: "transparent" }} />
            <span className="text-sm" style={{ color: "#8A8F98" }}>{tc("loading")}</span>
          </div>
        )}

        {!loading && (noSub || !sub) && (
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-sm" style={{ color: "#EDEDEF" }}>{t("free")}</p>
              <p className="text-xs mt-0.5" style={{ color: "#8A8F98" }}>{t("freeDescription")}</p>
            </div>
            <span
              className="text-xs font-medium px-2.5 py-1 rounded-full"
              style={{ background: "rgba(255,255,255,0.05)", color: "#8A8F98", border: "1px solid rgba(255,255,255,0.1)" }}
            >
              {t("free")}
            </span>
          </div>
        )}

        {!loading && sub && statusCfg && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="font-semibold text-sm" style={{ color: "#EDEDEF" }}>{t("planNumber", { id: sub.plan_id })}</p>
                {sub.current_period_end && (
                  <p className="text-xs mt-0.5" style={{ color: "#8A8F98" }}>
                    {t("renews", {
                      date: new Date(sub.current_period_end).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }),
                    })}
                  </p>
                )}
              </div>
              <span
                className="text-xs font-medium px-2.5 py-1 rounded-full"
                style={{ background: statusCfg.bg, color: statusCfg.color, border: `1px solid ${statusCfg.border}` }}
              >
                {statusCfg.label}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Upgrade plans */}
      <p className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: "#4A4F5A" }}>
        {t("upgradeTitle")}
      </p>
      <div className="grid grid-cols-2 gap-4 mb-6">
        {plans.map((plan) => (
          <div
            key={plan.key}
            className="p-5 rounded-2xl flex flex-col"
            style={{
              background: plan.highlight ? "rgba(99,102,241,0.08)" : "rgba(255,255,255,0.03)",
              border: plan.highlight ? "1px solid rgba(99,102,241,0.3)" : "1px solid rgba(255,255,255,0.08)",
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <p className="font-semibold text-sm" style={{ color: "#EDEDEF" }}>{plan.name}</p>
              <p className="text-sm font-bold" style={{ color: plan.highlight ? "#818CF8" : "#EDEDEF" }}>
                {plan.price}
              </p>
            </div>
            <ul className="flex flex-col gap-2 flex-1 mb-4">
              {plan.features.map((f) => (
                <li key={f} className="flex items-center gap-2 text-xs" style={{ color: "#8A8F98" }}>
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <circle cx="6" cy="6" r="5" fill={plan.highlight ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.05)"} stroke={plan.highlight ? "#6366F1" : "rgba(255,255,255,0.15)"} strokeWidth="0.8" />
                    <path d="M3.5 6l2 2 3-3" stroke={plan.highlight ? "#818CF8" : "#8A8F98"} strokeWidth="1" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {f}
                </li>
              ))}
            </ul>
            <button
              className="w-full py-2.5 rounded-xl text-xs font-semibold text-white transition-all duration-200"
              style={{
                background: plan.highlight
                  ? "linear-gradient(135deg, #6366F1, #4F46E5)"
                  : "rgba(255,255,255,0.08)",
                color: plan.highlight ? "white" : "#EDEDEF",
                boxShadow: plan.highlight ? "0 0 16px rgba(99,102,241,0.3)" : "none",
              }}
              onClick={() => alert(t("upgradeAlert", { name: plan.name }))}
              onMouseEnter={(e) => {
                if (!plan.highlight) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.12)";
              }}
              onMouseLeave={(e) => {
                if (!plan.highlight) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.08)";
              }}
            >
              {t("getPlan", { name: plan.name })}
            </button>
          </div>
        ))}
      </div>

      <p className="text-xs text-center" style={{ color: "#4A4F5A" }}>
        {t("paymentsFooter")}
      </p>
    </div>
  );
}
