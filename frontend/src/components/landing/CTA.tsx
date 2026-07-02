"use client";

export default function CTA() {
  return (
    <section
      className="relative py-32 px-6 overflow-hidden"
      style={{
        background:
          "linear-gradient(180deg, #08080C 0%, #0A0A12 50%, #08080C 100%)",
      }}
    >
      {/* Glow */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] rounded-full"
        style={{
          background: "radial-gradient(ellipse, rgba(99,102,241,0.2) 0%, transparent 70%)",
          filter: "blur(60px)",
        }}
      />

      <div className="max-w-3xl mx-auto text-center relative z-10">
        <h2
          className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight mb-6"
          style={{ color: "#EDEDEF" }}
        >
          Your next viral video starts with{" "}
          <span
            style={{
              background: "linear-gradient(135deg, #818CF8, #6366F1)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            a question
          </span>
        </h2>
        <p
          className="text-base md:text-lg mb-10 leading-relaxed"
          style={{ color: "#8A8F98" }}
        >
          Join thousands of creators turning hypothetical scenarios into captivating video podcasts. No editing skills, no production budget, no excuses.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <a
            href="/signup"
            className="flex items-center justify-center gap-2 px-8 py-4 rounded-xl text-base font-semibold text-white transition-all duration-300"
            style={{
              background: "linear-gradient(135deg, #6366F1, #4F46E5)",
              boxShadow: "0 0 40px rgba(99,102,241,0.4), 0 8px 32px rgba(0,0,0,0.4)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.boxShadow =
                "0 0 60px rgba(99,102,241,0.6), 0 8px 40px rgba(0,0,0,0.5)";
              (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.boxShadow =
                "0 0 40px rgba(99,102,241,0.4), 0 8px 32px rgba(0,0,0,0.4)";
              (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
            }}
          >
            Start for free — no credit card
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </a>
        </div>

        <p className="mt-6 text-xs" style={{ color: "#4A4F5A" }}>
          Free tier includes 1 episode/month. Upgrade anytime.
        </p>
      </div>
    </section>
  );
}
