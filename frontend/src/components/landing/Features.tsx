"use client";

const FEATURES = [
  {
    icon: "✦",
    title: "AI Scene Writing",
    description:
      "Describe your What If scenario and AI breaks it into compelling, structured scenes with narrative arc.",
    span: "col-span-2",
    accent: true,
  },
  {
    icon: "◈",
    title: "Cinematic Rendering",
    description:
      "Professional video output with dynamic visuals, transitions, and a soundtrack that fits your story.",
    span: "col-span-1",
    accent: false,
  },
  {
    icon: "▶",
    title: "YouTube Publishing",
    description:
      "One-click upload with AI-generated title, description, tags, and thumbnail. Your audience is waiting.",
    span: "col-span-1",
    accent: false,
  },
  {
    icon: "⬡",
    title: "Episode Library",
    description:
      "Organize, manage, and republish your content from a single dashboard.",
    span: "col-span-2",
    accent: false,
  },
  {
    icon: "◎",
    title: "Zero Skills Needed",
    description:
      "No video editing. No scriptwriting experience. No production crew. Just your ideas.",
    span: "col-span-1",
    accent: false,
  },
];

export default function Features() {
  return (
    <section
      id="features"
      className="relative py-32 px-6 overflow-hidden"
      style={{ background: "#08080C" }}
    >
      {/* Section heading */}
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <p
            className="text-xs font-semibold uppercase tracking-widest mb-4"
            style={{ color: "#6366F1" }}
          >
            Features
          </p>
          <h2
            className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight"
            style={{ color: "#EDEDEF" }}
          >
            Everything you need to go from{" "}
            <span
              style={{
                background: "linear-gradient(135deg, #818CF8, #6366F1)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              idea to published
            </span>
          </h2>
          <p className="text-base mt-4 max-w-xl mx-auto" style={{ color: "#8A8F98" }}>
            A complete production pipeline powered by AI — from your first sentence to a live video.
          </p>
        </div>

        {/* Bento Grid */}
        <div className="grid grid-cols-3 gap-4 auto-rows-auto">
          {FEATURES.map((f, i) => (
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
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
