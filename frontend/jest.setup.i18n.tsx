import React from "react";
import en from "./messages/en.json";

type Messages = Record<string, unknown>;

function resolve(ns: string | undefined, key: string): string {
  const path = ns ? `${ns}.${key}` : key;
  const value = path
    .split(".")
    .reduce<unknown>((acc, part) => (acc as Messages)?.[part as keyof Messages], en);
  return typeof value === "string" ? value : path;
}

// Do NOT spread jest.requireActual("next-intl") — the package is ESM and
// requireActual fails under Jest's CJS transform. Provide every export the
// app uses explicitly.
jest.mock("next-intl", () => ({
  useTranslations: (ns?: string) => {
    const t = (key: string, values?: Record<string, unknown>) => {
      let msg = resolve(ns, key);
      if (values) {
        for (const [k, v] of Object.entries(values)) {
          msg = msg.replaceAll(`{${k}}`, String(v));
        }
      }
      return msg;
    };
    t.rich = (key: string) => resolve(ns, key);
    return t;
  },
  useLocale: () => "en",
  NextIntlClientProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock("@/i18n/navigation", () => ({
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => (
    <a href={typeof href === "string" ? href : String(href)} {...rest}>
      {children}
    </a>
  ),
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/",
  redirect: jest.fn(),
}));
