"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getToken, logout } from "@/lib/auth";

const NAV = [
  {
    href: "/dashboard",
    label: "Episodes",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="3" width="12" height="2" rx="1" fill="currentColor" />
        <rect x="2" y="7" width="8" height="2" rx="1" fill="currentColor" />
        <rect x="2" y="11" width="10" height="2" rx="1" fill="currentColor" />
      </svg>
    ),
  },
  {
    href: "/dashboard/youtube",
    label: "YouTube",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path
          d="M14.5 4.5s-.2-1.2-.7-1.7c-.6-.7-1.3-.7-1.6-.7C10.5 2 8 2 8 2s-2.5 0-4.2.1c-.3 0-1 0-1.6.7-.5.5-.7 1.7-.7 1.7S1.3 5.8 1.3 7v1.1c0 1.2.2 2.5.2 2.5s.2 1.2.7 1.7c.6.7 1.5.6 1.8.7C5 13 8 13 8 13s2.5 0 4.2-.1c.3 0 1 0 1.6-.7.5-.5.7-1.7.7-1.7s.2-1.3.2-2.5V7c0-1.2-.2-2.5-.2-2.5zM6.5 9.8V5.5l4 2.2-4 2.1z"
          fill="currentColor"
        />
      </svg>
    ),
  },
  {
    href: "/dashboard/billing",
    label: "Billing",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="1" y="4" width="14" height="9" rx="2" stroke="currentColor" strokeWidth="1.5" fill="none" />
        <path d="M1 7h14" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    ),
  },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "#08080C" }}
      >
        <div
          className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: "#6366F1", borderTopColor: "transparent" }}
        />
      </div>
    );
  }

  return (
    <div
      className="min-h-screen flex"
      style={{ background: "#08080C" }}
    >
      {/* Sidebar */}
      <aside
        className="w-60 flex-shrink-0 flex flex-col py-6"
        style={{
          borderRight: "1px solid rgba(255,255,255,0.06)",
          background: "#0A0A0F",
        }}
      >
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 px-5 mb-8">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
            style={{
              background: "linear-gradient(135deg, #6366F1, #818CF8)",
              boxShadow: "0 0 14px rgba(99,102,241,0.35)",
            }}
          >
            W
          </div>
          <span className="font-semibold text-sm" style={{ color: "#EDEDEF" }}>
            What If<span style={{ color: "#818CF8" }}>?</span>
          </span>
        </Link>

        {/* Nav */}
        <nav className="flex-1 flex flex-col gap-1 px-3">
          {NAV.map((item) => {
            const active =
              item.href === "/dashboard"
                ? pathname === "/dashboard"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150"
                style={{
                  background: active ? "rgba(99,102,241,0.15)" : "transparent",
                  color: active ? "#818CF8" : "#8A8F98",
                  border: active
                    ? "1px solid rgba(99,102,241,0.2)"
                    : "1px solid transparent",
                }}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Sign out */}
        <div className="px-3 mt-4">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm w-full transition-all duration-150"
            style={{ color: "#4A4F5A" }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
              (e.currentTarget as HTMLElement).style.color = "#8A8F98";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = "transparent";
              (e.currentTarget as HTMLElement).style.color = "#4A4F5A";
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M6 14H3a1 1 0 01-1-1V3a1 1 0 011-1h3M10.5 11l3-3-3-3M13.5 8H6"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}
