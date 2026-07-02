"use client";

const STEPS = [
  {
    number: "01",
    title: "Write your What If",
    description:
      "Type any hypothetical scenario — \"What if electricity was never discovered?\" or \"What if humans colonized the ocean floor?\" The more specific, the more cinematic the result.",
    detail: "AI expands your premise into a 4-8 scene narrative structure with dramatic beats.",
  },
  {
    number: "02",
    title: "AI produces your episode",
    description:
      "Our pipeline writes scene-by-scene scripts, generates visuals, mixes narration, adds music, and renders a polished video — while you make a coffee.",
    detail: "Typical build time: 3–8 minutes per episode.",
  },
  {
    number: "03",
    title: "Publish to the world",
    description:
      "Connect your YouTube channel once. After that, publishing is a single click — title, description, tags, and thumbnail are all AI-generated and optimized for search.",
    detail: "Your video goes live while you're thinking about the next What If.",
  },
];

export default function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="relative py-32 px-6"
      style={{
        background:
          "linear-gradient(180deg, #08080C 0%, #0A0A0F 50%, #08080C 100%)",
      }}
    >
      <div className="max-w-7xl mx-auto">
        {/* Heading */}
        <div className="text-center mb-20">
          <p
            className="text-xs font-semibold uppercase tracking-widest mb-4"
            style={{ color: "#6366F1" }}
          >
            How It Works
          </p>
          <h2
            className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight"
            style={{ color: "#EDEDEF" }}
          >
            From idea to YouTube
            <br />
            <span
              style={{
                background: "linear-gradient(135deg, #818CF8, #6366F1)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              in under 10 minutes
            </span>
          </h2>
        </div>

        {/* Steps */}
        <div className="relative">
          {/* Vertical line */}
          <div
            className="hidden md:block absolute left-1/2 -translate-x-1/2 top-8 bottom-8 w-px"
            style={{
              background:
                "linear-gradient(180deg, transparent 0%, rgba(99,102,241,0.3) 15%, rgba(99,102,241,0.3) 85%, transparent 100%)",
            }}
          />

          <div className="flex flex-col gap-16">
            {STEPS.map((step, i) => (
              <div
                key={i}
                className={`relative flex flex-col md:flex-row items-start gap-8 md:gap-16 ${
                  i % 2 === 1 ? "md:flex-row-reverse" : ""
                }`}
              >
                {/* Content */}
                <div className="flex-1 md:text-right">
                  {i % 2 === 0 ? (
                    <StepContent step={step} align="right" />
                  ) : (
                    <div className="md:hidden">
                      <StepContent step={step} align="left" />
                    </div>
                  )}
                  {i % 2 !== 0 && (
                    <div className="hidden md:block">
                      <StepContent step={step} align="left" />
                    </div>
                  )}
                </div>

                {/* Center dot */}
                <div className="hidden md:flex flex-shrink-0 flex-col items-center">
                  <div
                    className="w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold"
                    style={{
                      background: "rgba(99,102,241,0.15)",
                      border: "1px solid rgba(99,102,241,0.4)",
                      color: "#818CF8",
                      boxShadow: "0 0 20px rgba(99,102,241,0.2)",
                    }}
                  >
                    {i + 1}
                  </div>
                </div>

                {/* Mirrored content */}
                <div className="flex-1">
                  {i % 2 === 1 ? (
                    <div className="hidden md:block">
                      <StepContent step={step} align="right" />
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function StepContent({
  step,
  align,
}: {
  step: (typeof STEPS)[0];
  align: "left" | "right";
}) {
  return (
    <div className={align === "right" ? "md:text-right" : "md:text-left"}>
      <span
        className="text-6xl font-black opacity-10 block leading-none mb-3"
        style={{ color: "#6366F1" }}
      >
        {step.number}
      </span>
      <h3
        className="text-xl font-bold mb-3 tracking-tight"
        style={{ color: "#EDEDEF" }}
      >
        {step.title}
      </h3>
      <p
        className="text-sm leading-relaxed mb-3 max-w-sm"
        style={{ color: "#8A8F98", marginLeft: align === "right" ? "auto" : undefined }}
      >
        {step.description}
      </p>
      <p
        className="text-xs"
        style={{
          color: "#6366F1",
          marginLeft: align === "right" ? "auto" : undefined,
        }}
      >
        {step.detail}
      </p>
    </div>
  );
}
