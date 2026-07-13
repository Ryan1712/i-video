import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "vi"],
  defaultLocale: "en",
  localePrefix: "always",
});

// next-intl 3.26.5 (the latest 3.x release, matching this project's pinned
// `^3.26.0`) does not export `hasLocale` from "next-intl" — that helper only
// shipped starting in next-intl v4. This is a drop-in equivalent type guard
// used by src/i18n/request.ts and src/app/[locale]/layout.tsx instead.
export function isLocale(value: string | undefined): value is (typeof routing.locales)[number] {
  return !!value && (routing.locales as readonly string[]).includes(value);
}
