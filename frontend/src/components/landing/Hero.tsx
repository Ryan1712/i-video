"use client";

import { useRef } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

export default function Hero() {
  const t = useTranslations("landing.hero");
  const stats = [0, 1, 2].map((i) => ({
    value: t(`stats.${i}.value`),
    label: t(`stats.${i}.label`),
  }));
  const videoRef = useRef<HTMLDivElement>(null);

  return (
    <section
      className="relative min-h-screen flex flex-col items-center justify-center px-6 pt-20 pb-16 overflow-hidden"
      style={{ background: "#08080C" }}
    >
      {/* Ambient blobs */}
      <div
        className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[500px] rounded-full opacity-20"
        style={{
          background:
            "radial-gradient(ellipse, #6366F1 0%, transparent 70%)",
          filter: "blur(80px)",
          animation: "blob-float 10s ease-in-out infinite",
        }}
      />
      <div
        className="absolute top-1/3 left-1/4 w-[400px] h-[400px] rounded-full opacity-10"
        style={{
          background:
            "radial-gradient(ellipse, #818CF8 0%, transparent 70%)",
          filter: "blur(60px)",
          animation: "blob-float 14s ease-in-out infinite reverse",
        }}
      />
      <div
        className="absolute top-1/2 right-1/4 w-[300px] h-[300px] rounded-full opacity-8"
        style={{
          background:
            "radial-gradient(ellipse, #4F46E5 0%, transparent 70%)",
          filter: "blur(60px)",
          animation: "blob-float 12s ease-in-out infinite",
          animationDelay: "4s",
        }}
      />

      {/* Badge */}
      <div className="animate-fade-up animate-delay-100 mb-8 relative z-10">
        <div
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium"
          style={{
            background: "rgba(99,102,241,0.12)",
            border: "1px solid rgba(99,102,241,0.3)",
            color: "#818CF8",
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full bg-[#6366F1]"
            style={{ boxShadow: "0 0 6px #6366F1" }}
          />
          {t("badge")}
        </div>
      </div>

      {/* Headline */}
      <div className="relative z-10 text-center max-w-4xl mx-auto animate-fade-up animate-delay-200">
        <h1
          className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-tight mb-6"
          style={{ color: "#EDEDEF" }}
        >
          {t("title")}
        </h1>
        <p
          className="text-lg md:text-xl leading-relaxed max-w-2xl mx-auto"
          style={{ color: "#8A8F98" }}
        >
          {t("subtitle")}
        </p>
      </div>

      {/* CTAs */}
      <div className="relative z-10 flex flex-col sm:flex-row gap-4 mt-10 animate-fade-up animate-delay-300">
        <Link
          href="/signup"
          className="flex items-center justify-center gap-2 px-7 py-3.5 rounded-xl text-sm font-semibold text-white transition-all duration-300"
          style={{
            background: "linear-gradient(135deg, #6366F1, #4F46E5)",
            boxShadow: "0 0 32px rgba(99,102,241,0.35), 0 4px 16px rgba(0,0,0,0.3)",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.boxShadow =
              "0 0 48px rgba(99,102,241,0.55), 0 4px 24px rgba(0,0,0,0.4)";
            (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.boxShadow =
              "0 0 32px rgba(99,102,241,0.35), 0 4px 16px rgba(0,0,0,0.3)";
            (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
          }}
        >
          {t("cta")}
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </Link>
        <a
          href="#how"
          className="flex items-center justify-center gap-2 px-7 py-3.5 rounded-xl text-sm font-medium transition-all duration-200"
          style={{
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "#EDEDEF",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.08)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)";
          }}
        >
          {t("ctaSecondary")}
        </a>
      </div>

      {/* Stats */}
      <div className="relative z-10 mt-16 flex flex-col items-center gap-4 animate-fade-up animate-delay-400">
        <div className="flex items-center gap-8 md:gap-16">
          {stats.map((stat, i) => (
            <div key={i} className="text-center">
              <p
                className="text-2xl md:text-3xl font-bold"
                style={{
                  background: "linear-gradient(135deg, #EDEDEF 0%, #8A8F98 100%)",
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                }}
              >
                {stat.value}
              </p>
              <p className="text-xs mt-1" style={{ color: "#4A4F5A" }}>
                {stat.label}
              </p>
            </div>
          ))}
        </div>
        <p className="text-xs" style={{ color: "#4A4F5A" }}>
          {t("statsNote")}
        </p>
      </div>

      {/* Video mockup */}
      <div
        ref={videoRef}
        className="relative z-10 mt-20 w-full max-w-5xl mx-auto animate-fade-up animate-delay-500"
      >
        <div
          className="relative rounded-2xl overflow-hidden"
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.08)",
            boxShadow:
              "0 0 0 1px rgba(255,255,255,0.04), 0 32px 80px rgba(0,0,0,0.6), 0 0 80px rgba(99,102,241,0.08)",
          }}
        >
          {/* Browser chrome */}
          <div
            className="flex items-center gap-2 px-4 py-3"
            style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
          >
            <div className="w-3 h-3 rounded-full" style={{ background: "#EF4444", opacity: 0.7 }} />
            <div className="w-3 h-3 rounded-full" style={{ background: "#F59E0B", opacity: 0.7 }} />
            <div className="w-3 h-3 rounded-full" style={{ background: "#10B981", opacity: 0.7 }} />
            <div
              className="mx-4 flex-1 max-w-sm rounded-md px-3 py-1 text-xs"
              style={{
                background: "rgba(255,255,255,0.05)",
                color: "#4A4F5A",
              }}
            >
              app.narro.app/series/the-signal/episode-4
            </div>
          </div>

          {/* App UI mockup */}
          <div
            className="grid grid-cols-5 min-h-[360px]"
            style={{ background: "#0A0A0F" }}
          >
            {/* Sidebar */}
            <div
              className="col-span-1 p-4 flex flex-col gap-3"
              style={{ borderRight: "1px solid rgba(255,255,255,0.06)" }}
            >
              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "#4A4F5A" }}>
                Episodes
              </p>
              {[
                { title: "Episode 4: The Signal", active: true },
                { title: "Episode 3: Nightfall", active: false },
                { title: "Episode 2: First Contact", active: false },
              ].map((ep, i) => (
                <div
                  key={i}
                  className="p-2 rounded-lg text-xs truncate transition-all"
                  style={{
                    background: ep.active
                      ? "rgba(99,102,241,0.15)"
                      : "transparent",
                    border: ep.active
                      ? "1px solid rgba(99,102,241,0.25)"
                      : "1px solid transparent",
                    color: ep.active ? "#818CF8" : "#8A8F98",
                  }}
                >
                  {ep.title}
                </div>
              ))}
            </div>

            {/* Main area */}
            <div className="col-span-4 p-6 flex flex-col gap-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-sm mb-1" style={{ color: "#EDEDEF" }}>
                    Episode 4: The Signal
                  </h3>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{
                        background: "rgba(16,185,129,0.12)",
                        color: "#10B981",
                        border: "1px solid rgba(16,185,129,0.25)",
                      }}
                    >
                      ✓ Published
                    </span>
                    <span className="text-xs" style={{ color: "#4A4F5A" }}>
                      4 scenes · 8 min
                    </span>
                  </div>
                </div>
                <div
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{
                    background: "rgba(99,102,241,0.15)",
                    border: "1px solid rgba(99,102,241,0.3)",
                    color: "#818CF8",
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                    <path d="M4.5 2.5l5 3.5-5 3.5V2.5z"/>
                  </svg>
                  YouTube
                </div>
              </div>

              {/* Scenes */}
              <div className="grid grid-cols-2 gap-3 mt-2">
                {[
                  { title: "The Last Connection", status: "done" },
                  { title: "Cities Go Silent", status: "done" },
                  { title: "The Recovery Plan", status: "done" },
                  { title: "A New Internet Age", status: "done" },
                ].map((scene, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl flex items-center gap-3"
                    style={{
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.06)",
                    }}
                  >
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0"
                      style={{
                        background: "rgba(99,102,241,0.15)",
                        color: "#818CF8",
                      }}
                    >
                      {i + 1}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium truncate" style={{ color: "#EDEDEF" }}>
                        {scene.title}
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: "#4A4F5A" }}>
                        Rendered
                      </p>
                    </div>
                    <div className="ml-auto">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="#10B981">
                        <circle cx="7" cy="7" r="6" fill="rgba(16,185,129,0.15)" stroke="#10B981" strokeWidth="1"/>
                        <path d="M4.5 7l2 2 3-3" stroke="#10B981" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Glow under the mockup */}
        <div
          className="absolute -bottom-16 left-1/2 -translate-x-1/2 w-3/4 h-32 rounded-full opacity-30"
          style={{
            background: "radial-gradient(ellipse, #6366F1 0%, transparent 70%)",
            filter: "blur(40px)",
          }}
        />
      </div>
    </section>
  );
}
