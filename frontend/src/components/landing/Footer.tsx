"use client";

import { useTranslations } from "next-intl";
import Logo from "@/components/Logo";

export default function Footer() {
  const t = useTranslations("landing");
  const links = {
    Product: ["Features", "Pricing", "Changelog", "Roadmap"],
    Resources: ["Documentation", "API Reference", "Status", "Blog"],
    Company: ["About", "Careers", "Privacy", "Terms"],
  };
  const year = new Date().getFullYear();

  return (
    <footer
      className="py-16 px-6"
      style={{
        borderTop: "1px solid rgba(255,255,255,0.06)",
        background: "#08080C",
      }}
    >
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-12 mb-16">
          {/* Brand */}
          <div className="col-span-2 md:col-span-1">
            <div className="mb-4">
              <Logo size={24} />
            </div>
            <p className="text-sm leading-relaxed" style={{ color: "#4A4F5A" }}>
              {t("footer.tagline")}
            </p>
          </div>

          {/* Link columns */}
          {Object.entries(links).map(([section, items]) => (
            <div key={section}>
              <p
                className="text-xs font-semibold uppercase tracking-widest mb-4"
                style={{ color: "#4A4F5A" }}
              >
                {section}
              </p>
              <ul className="flex flex-col gap-3">
                {items.map((item) => (
                  <li key={item}>
                    <a
                      href="#"
                      className="text-sm transition-colors duration-200"
                      style={{ color: "#8A8F98" }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.color = "#EDEDEF")
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.color = "#8A8F98")
                      }
                    >
                      {item}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div
          className="flex flex-col md:flex-row items-center justify-between gap-4 pt-8"
          style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
        >
          <p className="text-xs" style={{ color: "#4A4F5A" }}>
            © {year} Narro. {t("footer.rights")}
          </p>
          <p className="text-xs" style={{ color: "#4A4F5A" }}>
            {t("footer.taglineShort")}
          </p>
        </div>
      </div>
    </footer>
  );
}
