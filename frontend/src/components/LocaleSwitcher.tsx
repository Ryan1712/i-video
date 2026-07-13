"use client";

import { useLocale } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";

const LOCALES = ["en", "vi"] as const;

export default function LocaleSwitcher() {
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <span
      className="inline-flex rounded-lg overflow-hidden text-xs font-semibold"
      style={{ border: "1px solid rgba(255,255,255,0.1)" }}
    >
      {LOCALES.map((l) => (
        <button
          key={l}
          onClick={() => l !== locale && router.replace(pathname, { locale: l })}
          className="px-2.5 py-1.5 uppercase"
          style={{
            background: l === locale ? "rgba(99,102,241,0.2)" : "transparent",
            color: l === locale ? "#818CF8" : "#8A8F98",
          }}
        >
          {l.toUpperCase()}
        </button>
      ))}
    </span>
  );
}
