"use client";

import { useTranslations } from "next-intl";

export default function HowItWorks() {
  const t = useTranslations("landing.how");
  const steps = [0, 1, 2, 3].map((i) => ({
    title: t(`steps.${i}.title`),
    body: t(`steps.${i}.body`),
  }));

  return (
    <section
      id="how"
      className="relative py-32 px-6"
      style={{
        background:
          "linear-gradient(180deg, #08080C 0%, #0A0A0F 50%, #08080C 100%)",
      }}
    >
      <div className="max-w-7xl mx-auto">
        {/* Heading */}
        <div className="text-center mb-20">
          <h2
            className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight"
            style={{ color: "#EDEDEF" }}
          >
            {t("title")}
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
            {steps.map((step, i) => (
              <div
                key={i}
                className={`relative flex flex-col md:flex-row items-start gap-8 md:gap-16 ${
                  i % 2 === 1 ? "md:flex-row-reverse" : ""
                }`}
              >
                {/* Content */}
                <div className="flex-1">
                  <StepContent step={step} number={i + 1} align={i % 2 === 0 ? "right" : "left"} />
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

                {/* Spacer to keep the dot centered */}
                <div className="hidden md:block flex-1" />
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
  number,
  align,
}: {
  step: { title: string; body: string };
  number: number;
  align: "left" | "right";
}) {
  return (
    <div className={align === "right" ? "md:text-right" : "md:text-left"}>
      <span
        className="text-6xl font-black opacity-10 block leading-none mb-3"
        style={{ color: "#6366F1" }}
      >
        {String(number).padStart(2, "0")}
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
        {step.body}
      </p>
    </div>
  );
}
