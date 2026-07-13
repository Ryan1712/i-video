"use client";

import { useState, useEffect } from "react";
import { Link } from "@/i18n/navigation";
import Logo from "@/components/Logo";
import LocaleSwitcher from "@/components/LocaleSwitcher";

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled
          ? "rgba(8,8,12,0.85)"
          : "transparent",
        backdropFilter: scrolled ? "blur(20px)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(20px)" : "none",
        borderBottom: scrolled
          ? "1px solid rgba(255,255,255,0.06)"
          : "1px solid transparent",
      }}
    >
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="group">
          <Logo size={32} />
        </Link>

        {/* Links */}
        <div className="hidden md:flex items-center gap-8">
          {["Features", "How It Works", "Pricing"].map((item) => (
            <a
              key={item}
              href={`#${item.toLowerCase().replace(/\s+/g, "-")}`}
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
          ))}
        </div>

        {/* CTAs */}
        <div className="flex items-center gap-3">
          <LocaleSwitcher />
          <Link
            href="/login"
            className="hidden md:block text-sm transition-colors duration-200"
            style={{ color: "#8A8F98" }}
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-all duration-200"
            style={{
              background: "linear-gradient(135deg, #6366F1, #4F46E5)",
              boxShadow: "0 0 20px rgba(99,102,241,0.25)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.boxShadow =
                "0 0 30px rgba(99,102,241,0.45)";
              (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.boxShadow =
                "0 0 20px rgba(99,102,241,0.25)";
              (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
            }}
          >
            Get started free
          </Link>
        </div>
      </div>
    </nav>
  );
}
