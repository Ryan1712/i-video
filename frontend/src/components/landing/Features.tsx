"use client";

import { useTranslations } from "next-intl";

const ICONS = ["✦", "◈", "◎", "⬡", "▶", "✓"];
const SPANS = ["col-span-2", "col-span-1", "col-span-1", "col-span-2", "col-span-1", "col-span-1"];
const ACCENTS = [true, false, false, false, false, false];

export default function Features() {
  const t = useTranslations("landing.features");
  const items = [0, 1, 2, 3, 4, 5].map((i) => ({
    title: t(`items.${i}.title`),
    body: t(`items.${i}.body`),
    icon: ICONS[i],
    span: SPANS[i],
    accent: ACCENTS[i],
  }));

  return (
    <section
      id="features"
      className="relative py-32 px-6 overflow-hidden"
      style={{ background: "#08080C" }}
    >
      {/* Section heading */}
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2
            className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight"
            style={{ color: "#EDEDEF" }}
          >
            {t("title")}
          </h2>
        </div>

        {/* Bento Grid */}
        <div className="grid grid-cols-3 gap-4 auto-rows-auto">
          {items.map((f, i) => (
            <div
              key={i}
              className={`${f.span} p-8 rounded-2xl relative overflow-hidden group transition-all duration-300`}
              style={{
                background: f.accent
                  ? "linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(79,70,229,0.08) 100%)"
                  : "rgba(255,255,255,0.03)",
                border: f.accent
                  ? "1px solid rgba(99,102,241,0.3)"
                  : "1px solid rgba(255,255,255,0.07)",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = f.accent
                  ? "linear-gradient(135deg, rgba(99,102,241,0.22) 0%, rgba(79,70,229,0.12) 100%)"
                  : "rgba(255,255,255,0.055)";
                (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = f.accent
                  ? "linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(79,70,229,0.08) 100%)"
                  : "rgba(255,255,255,0.03)";
                (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
              }}
            >
              {f.accent && (
                <div
                  className="absolute -top-12 -right-12 w-40 h-40 rounded-full opacity-20"
                  style={{
                    background: "radial-gradient(circle, #6366F1 0%, transparent 70%)",
                    filter: "blur(24px)",
                  }}
                />
              )}
              <div
                className="text-2xl mb-4"
                style={{ color: f.accent ? "#818CF8" : "#6366F1" }}
              >
                {f.icon}
              </div>
              <h3
                className="text-lg font-semibold mb-2 tracking-tight"
                style={{ color: "#EDEDEF" }}
              >
                {f.title}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: "#8A8F98" }}>
                {f.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
