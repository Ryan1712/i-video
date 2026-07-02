"use client";

const PLANS = [
  {
    name: "Free",
    price: "0",
    billing: "forever",
    description: "Start exploring What If without a credit card.",
    features: [
      "1 episode per month",
      "Up to 4 scenes per episode",
      "720p video output",
      "Watermarked export",
      "Community support",
    ],
    cta: "Start for free",
    popular: false,
    href: "/signup",
  },
  {
    name: "Creator",
    price: "19",
    billing: "per month",
    description: "For creators who publish consistently.",
    features: [
      "10 episodes per month",
      "Up to 8 scenes per episode",
      "1080p video output",
      "No watermark",
      "YouTube auto-publish",
      "Priority rendering",
      "Email support",
    ],
    cta: "Get Creator",
    popular: true,
    href: "/signup?plan=creator",
  },
  {
    name: "Studio",
    price: "49",
    billing: "per month",
    description: "For studios and agencies at scale.",
    features: [
      "Unlimited episodes",
      "Unlimited scenes",
      "4K video output",
      "No watermark",
      "YouTube + multi-platform",
      "Fastest rendering queue",
      "Custom branding",
      "Dedicated support",
    ],
    cta: "Get Studio",
    popular: false,
    href: "/signup?plan=studio",
  },
];

export default function Pricing() {
  return (
    <section
      id="pricing"
      className="relative py-32 px-6 overflow-hidden"
      style={{ background: "#08080C" }}
    >
      {/* Ambient glow */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full opacity-10"
        style={{
          background: "radial-gradient(ellipse, #6366F1 0%, transparent 70%)",
          filter: "blur(80px)",
        }}
      />

      <div className="max-w-7xl mx-auto relative z-10">
        {/* Heading */}
        <div className="text-center mb-16">
          <p
            className="text-xs font-semibold uppercase tracking-widest mb-4"
            style={{ color: "#6366F1" }}
          >
            Pricing
          </p>
          <h2
            className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight"
            style={{ color: "#EDEDEF" }}
          >
            Simple, transparent pricing
          </h2>
          <p className="text-base mt-4 max-w-xl mx-auto" style={{ color: "#8A8F98" }}>
            No hidden fees. No per-minute charges. Just a flat plan that scales with your ambition.
          </p>
        </div>

        {/* Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className="relative rounded-2xl p-8 flex flex-col transition-all duration-300"
              style={{
                background: plan.popular
                  ? "linear-gradient(135deg, rgba(99,102,241,0.14) 0%, rgba(79,70,229,0.08) 100%)"
                  : "rgba(255,255,255,0.03)",
                border: plan.popular
                  ? "1px solid rgba(99,102,241,0.4)"
                  : "1px solid rgba(255,255,255,0.08)",
                boxShadow: plan.popular
                  ? "0 0 40px rgba(99,102,241,0.12)"
                  : "none",
              }}
            >
              {plan.popular && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
                  <span
                    className="px-4 py-1 rounded-full text-xs font-semibold text-white"
                    style={{
                      background: "linear-gradient(135deg, #6366F1, #4F46E5)",
                      boxShadow: "0 0 16px rgba(99,102,241,0.4)",
                    }}
                  >
                    Most Popular
                  </span>
                </div>
              )}

              <div className="mb-6">
                <h3
                  className="text-sm font-semibold mb-2 uppercase tracking-widest"
                  style={{ color: plan.popular ? "#818CF8" : "#8A8F98" }}
                >
                  {plan.name}
                </h3>
                <div className="flex items-end gap-1 mb-2">
                  <span
                    className="text-4xl font-bold"
                    style={{ color: "#EDEDEF" }}
                  >
                    ${plan.price}
                  </span>
                  <span className="text-sm mb-1.5" style={{ color: "#4A4F5A" }}>
                    /{plan.billing}
                  </span>
                </div>
                <p className="text-sm" style={{ color: "#8A8F98" }}>
                  {plan.description}
                </p>
              </div>

              <ul className="flex flex-col gap-3 mb-8 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm">
                    <svg
                      className="flex-shrink-0 mt-0.5"
                      width="14"
                      height="14"
                      viewBox="0 0 14 14"
                      fill="none"
                    >
                      <circle
                        cx="7"
                        cy="7"
                        r="6"
                        fill={plan.popular ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.05)"}
                        stroke={plan.popular ? "#6366F1" : "rgba(255,255,255,0.15)"}
                        strokeWidth="1"
                      />
                      <path
                        d="M4.5 7l2 2 3-3"
                        stroke={plan.popular ? "#818CF8" : "#8A8F98"}
                        strokeWidth="1.2"
                        fill="none"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    <span style={{ color: "#EDEDEF" }}>{f}</span>
                  </li>
                ))}
              </ul>

              <a
                href={plan.href}
                className="block w-full py-3 rounded-xl text-sm font-semibold text-center transition-all duration-200"
                style={
                  plan.popular
                    ? {
                        background: "linear-gradient(135deg, #6366F1, #4F46E5)",
                        color: "#fff",
                        boxShadow: "0 0 24px rgba(99,102,241,0.3)",
                      }
                    : {
                        background: "rgba(255,255,255,0.06)",
                        color: "#EDEDEF",
                        border: "1px solid rgba(255,255,255,0.1)",
                      }
                }
                onMouseEnter={(e) => {
                  if (plan.popular) {
                    (e.currentTarget as HTMLElement).style.boxShadow =
                      "0 0 36px rgba(99,102,241,0.5)";
                  } else {
                    (e.currentTarget as HTMLElement).style.background =
                      "rgba(255,255,255,0.1)";
                  }
                  (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)";
                }}
                onMouseLeave={(e) => {
                  if (plan.popular) {
                    (e.currentTarget as HTMLElement).style.boxShadow =
                      "0 0 24px rgba(99,102,241,0.3)";
                  } else {
                    (e.currentTarget as HTMLElement).style.background =
                      "rgba(255,255,255,0.06)";
                  }
                  (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
                }}
              >
                {plan.cta}
              </a>
            </div>
          ))}
        </div>

        <p className="text-center mt-8 text-sm" style={{ color: "#4A4F5A" }}>
          All plans include a 14-day free trial. No credit card required for Free tier.
        </p>
      </div>
    </section>
  );
}
