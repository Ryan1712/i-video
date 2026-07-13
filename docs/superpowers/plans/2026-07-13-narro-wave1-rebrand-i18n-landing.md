# Narro Wave 1: Rebrand + i18n + Landing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the frontend from "What If?" to Narro, add next-intl EN/VI localization with `/[locale]` routing, and rewrite the landing page to the "consistent series" positioning.

**Architecture:** Spec: `docs/superpowers/specs/2026-07-13-narro-frontend-redesign-design.md` (Wave 1 only — wizard/settings/voice picker are Wave 2, OUT of this plan). All routes move under `src/app/[locale]/`; next-intl middleware handles locale detection (must NOT touch `/api/*` — that's the backend proxy rewrite). UI strings live in `messages/en.json` / `messages/vi.json`. A shared `Logo` component and a `LocaleSwitcher` component are reused across landing and dashboard. Backend untouched.

**Tech Stack:** Next.js 14.2 App Router, next-intl v3, Tailwind (existing inline-style conventions), Jest + Testing Library, Playwright.

## Global Constraints

- Work on branch `phase1-series-agent` in `D:\Video\agent_video`. Frontend commands run from `D:\Video\agent_video\frontend`.
- Product name is exactly **Narro**. After Wave 1, `grep -ri "what if" frontend/src` may match ONLY: user content placeholders (e.g. episode-title example text) — zero matches in branding, metadata, logos, nav, footer.
- Locales exactly `en` (default) and `vi`; routing prefix always (`/en/...`, `/vi/...`); middleware matcher MUST exclude `/api`, `_next`, and files with extensions: `matcher: ["/((?!api|_next|.*\\..*).*)"]`.
- Landing copy promises ONLY shipped features (AI script to length with user review, scene split + asset matching, image generation, multi-language TTS, exact subtitles, YouTube upload). NO timeline-editor claims. Hero stats are the three pilot facts with the note "from our pilot episode" / "từ tập thí điểm của chúng tôi".
- Internal navigation in migrated components uses the wrappers from `@/i18n/navigation` (NOT `next/link` / `next/navigation`) so locale prefixes are preserved.
- All Jest suites and `npm run build` must pass at the end of every task (build gate enforced from Task 1 on; Task 6 additionally fixes the pre-existing lint errors that block `next build`).
- Commit messages follow `feat(scope): ...` / `fix(scope): ...`. Commit ONLY files your task touches — never `.claude/`, `docker-compose.override.yml`, `frontend/test-results/`, `videos/`, old plan docs.

## File Structure (end state of Wave 1)

```
frontend/
  messages/en.json            # all UI strings, EN
  messages/vi.json            # all UI strings, VI
  src/middleware.ts           # next-intl locale middleware
  src/i18n/routing.ts         # locales/defaultLocale/localePrefix
  src/i18n/request.ts         # message loading per request
  src/i18n/navigation.ts      # Link/useRouter/usePathname/redirect wrappers
  src/app/layout.tsx          # passthrough root layout (html lives in [locale])
  src/app/[locale]/layout.tsx # html/body + NextIntlClientProvider + Narro metadata
  src/app/[locale]/page.tsx   # landing
  src/app/[locale]/(auth)/... # login/signup (moved)
  src/app/[locale]/dashboard/...  # all dashboard pages (moved)
  src/app/icon.svg            # Narro "N" favicon
  src/components/Logo.tsx     # N mark + wordmark, size prop
  src/components/LocaleSwitcher.tsx
  src/components/landing/*    # rewritten copy via useTranslations
  jest.setup.i18n.tsx         # global next-intl + @/i18n/navigation mocks
```

---

### Task 1: next-intl scaffolding + `[locale]` migration

**Files:**
- Modify: `frontend/package.json` (add `next-intl@^3.26.0`), `frontend/next.config.mjs`, `frontend/jest.config.ts`, `frontend/src/lib/auth.ts`
- Create: `frontend/src/i18n/routing.ts`, `frontend/src/i18n/request.ts`, `frontend/src/i18n/navigation.ts`, `frontend/src/middleware.ts`, `frontend/messages/en.json`, `frontend/messages/vi.json`, `frontend/jest.setup.i18n.tsx`, `frontend/src/app/[locale]/layout.tsx`
- Move (git mv): `src/app/page.tsx → src/app/[locale]/page.tsx`, `src/app/(auth) → src/app/[locale]/(auth)`, `src/app/dashboard → src/app/[locale]/dashboard`
- Rewrite: `frontend/src/app/layout.tsx` (passthrough)
- Test: `frontend/src/__tests__/i18n-routing.test.tsx`

**Interfaces:**
- Produces: `@/i18n/navigation` exporting `Link`, `useRouter`, `usePathname`, `redirect` (same call signatures as next's — later tasks import these); `useTranslations` usable in any client component under `[locale]`; message namespaces `common`, `auth` defined below; global Jest mocks so existing suites keep passing without per-file changes.

- [ ] **Step 1: Install and write the failing test**

Run: `npm install next-intl@^3.26.0` (from `frontend/`)

Create `frontend/src/__tests__/i18n-routing.test.tsx`:

```tsx
import { routing } from "@/i18n/routing";
import en from "../../messages/en.json";
import vi from "../../messages/vi.json";

describe("i18n configuration", () => {
  it("declares exactly en (default) and vi", () => {
    expect(routing.locales).toEqual(["en", "vi"]);
    expect(routing.defaultLocale).toBe("en");
  });

  it("vi covers every key en has (no missing translations)", () => {
    function keys(obj: Record<string, unknown>, prefix = ""): string[] {
      return Object.entries(obj).flatMap(([k, v]) =>
        typeof v === "object" && v !== null
          ? keys(v as Record<string, unknown>, `${prefix}${k}.`)
          : [`${prefix}${k}`]
      );
    }
    expect(keys(vi).sort()).toEqual(keys(en).sort());
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- i18n-routing`
Expected: FAIL — `@/i18n/routing` not found

- [ ] **Step 3: Create the i18n config files**

`frontend/src/i18n/routing.ts`:

```ts
import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "vi"],
  defaultLocale: "en",
  localePrefix: "always",
});
```

`frontend/src/i18n/request.ts`:

```ts
import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
```

`frontend/src/i18n/navigation.ts`:

```ts
import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

export const { Link, redirect, usePathname, useRouter } = createNavigation(routing);
```

`frontend/src/middleware.ts`:

```ts
import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // NEVER match /api (proxied to FastAPI by the rewrite), _next, or static files.
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
```

In `frontend/next.config.mjs`, wrap with the plugin (keep the existing rewrites unchanged):

```js
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
```

- [ ] **Step 4: Seed the message catalogs**

`frontend/messages/en.json`:

```json
{
  "common": {
    "appName": "Narro",
    "login": "Log in",
    "signup": "Sign up",
    "logout": "Sign out",
    "loading": "Loading…"
  },
  "auth": {
    "loginTitle": "Welcome back",
    "signupTitle": "Create your account",
    "email": "Email",
    "password": "Password",
    "loginButton": "Log in",
    "signupButton": "Create account",
    "haveAccount": "Already have an account?",
    "noAccount": "No account yet?"
  }
}
```

`frontend/messages/vi.json`:

```json
{
  "common": {
    "appName": "Narro",
    "login": "Đăng nhập",
    "signup": "Đăng ký",
    "logout": "Đăng xuất",
    "loading": "Đang tải…"
  },
  "auth": {
    "loginTitle": "Chào mừng trở lại",
    "signupTitle": "Tạo tài khoản",
    "email": "Email",
    "password": "Mật khẩu",
    "loginButton": "Đăng nhập",
    "signupButton": "Tạo tài khoản",
    "haveAccount": "Đã có tài khoản?",
    "noAccount": "Chưa có tài khoản?"
  }
}
```

(Later tasks EXTEND these files — never rename existing keys.)

- [ ] **Step 5: Move the route tree under `[locale]`**

```bash
git mv src/app/page.tsx "src/app/[locale]/page.tsx"
git mv "src/app/(auth)" "src/app/[locale]/(auth)"
git mv src/app/dashboard "src/app/[locale]/dashboard"
```

Rewrite `frontend/src/app/layout.tsx` to a passthrough (html moves to the locale layout):

```tsx
// Root layout is a passthrough; <html> lives in [locale]/layout.tsx so the
// lang attribute matches the active locale.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
```

Create `frontend/src/app/[locale]/layout.tsx` — copy the ORIGINAL root layout's `<html>/<body>` structure, fonts, and globals.css import, then wrap children:

```tsx
import type { Metadata } from "next";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { notFound } from "next/navigation";
import { routing } from "@/i18n/routing";
import "../globals.css";

export const metadata: Metadata = {
  title: "Narro — Turn one idea into a whole series",
  description:
    "AI writes the script, you approve it, Narro builds the video and publishes to YouTube — with consistent characters and voice across every episode.",
};

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { locale: string };
}) {
  const { locale } = params;
  if (!hasLocale(routing.locales, locale)) notFound();

  const messages = (await import(`../../../messages/${locale}.json`)).default;

  return (
    <html lang={locale}>
      <body className="antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
```

IMPORTANT: check the original `src/app/layout.tsx` before overwriting — if it loads local fonts (`./fonts/...`) or extra classNames on `<body>`, carry them into `[locale]/layout.tsx` verbatim (fonts path becomes `../fonts/...` relative to the new file).

- [ ] **Step 6: Point internal navigation at the locale-aware wrappers**

In every moved page/layout that imports `next/link` or `next/navigation` (`[locale]/(auth)/login/page.tsx`, `signup/page.tsx`, `(auth)/layout.tsx`, `[locale]/page.tsx`, `[locale]/dashboard/layout.tsx`, `dashboard/page.tsx`, `dashboard/episodes/new/page.tsx`, `dashboard/episodes/[id]/page.tsx`, `dashboard/series/page.tsx`, `dashboard/series/[id]/page.tsx`, `dashboard/youtube/page.tsx`, `dashboard/billing/page.tsx`, plus `components/landing/*.tsx` and `components/episode/ScriptPanel.tsx` if they navigate):

- `import Link from "next/link"` → `import { Link } from "@/i18n/navigation"`
- `import { useRouter, usePathname } from "next/navigation"` → same names from `"@/i18n/navigation"`
- EXCEPTIONS: `useParams` and `useSearchParams` stay on `next/navigation` (next-intl has no wrappers for them); `notFound` stays on `next/navigation`.

In `frontend/src/lib/auth.ts`, `logout()` keeps `window.location.href = "/login"` — the middleware redirects it to the default locale; add the comment:

```ts
export function logout() {
  clearToken();
  // Middleware rewrites this to /<defaultLocale>/login; acceptable to lose
  // the active locale on logout (Wave 2 may read the cookie instead).
  window.location.href = "/login";
}
```

- [ ] **Step 7: Global Jest mocks so the existing 6 suites keep passing**

Create `frontend/jest.setup.i18n.tsx`:

```tsx
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
```

In `frontend/jest.config.ts`, add the file to `setupFilesAfterEach`/`setupFilesAfterEnv` (append to the existing array — read the config first; it already has a setup file for testing-library):

```ts
setupFilesAfterEnv: ["<rootDir>/jest.setup.ts", "<rootDir>/jest.setup.i18n.tsx"],
```

(If the existing setup file has a different name, keep it and append ours.)

Existing test files import pages from `@/app/dashboard/...` — update those import paths to `@/app/[locale]/dashboard/...` (files: `dashboard.test.tsx`, `new-episode.test.tsx`, `series.test.tsx`, and any other page imports; `login.test.tsx`/`signup.test.tsx` → `@/app/[locale]/(auth)/...`). Do NOT change test assertions in this task.

- [ ] **Step 8: Run all tests + build**

Run: `npm test` — all suites pass (existing assertions untouched; pages don't use useTranslations yet, mocks are inert).
Run: `npm run build` — compile must succeed. If ONLY the pre-existing lint errors fail the build (unused vars in `dashboard.test.tsx:83`/`new-episode.test.tsx`, exhaustive-deps warning), note them in your report — they are fixed in Task 6; verify compile success with `npx next build --no-lint` in that case.
Manual smoke: `npm run dev`, open `http://localhost:3000/` → expect redirect to `/en`; `http://localhost:3000/vi/dashboard` renders; `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/series` still returns 401 (middleware didn't swallow the proxy).

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src frontend/messages frontend/package.json frontend/package-lock.json frontend/next.config.mjs frontend/jest.config.ts frontend/jest.setup.i18n.tsx
git commit -m "feat(i18n): next-intl scaffolding, [locale] routing, EN/VI catalogs"
```

---

### Task 2: Logo component + Narro rebrand of app chrome

**Files:**
- Create: `frontend/src/components/Logo.tsx`, `frontend/src/app/icon.svg`
- Modify: `frontend/src/app/[locale]/dashboard/layout.tsx` (sidebar logo + nav labels via t()), `frontend/src/app/[locale]/(auth)/layout.tsx` (logo), `frontend/src/components/landing/Nav.tsx` (logo only — full copy rewrite is Task 4), `frontend/src/components/landing/Footer.tsx` (logo + name only), `frontend/messages/en.json`, `frontend/messages/vi.json`
- Test: `frontend/src/__tests__/logo.test.tsx`

**Interfaces:**
- Produces: `<Logo size={number} withWordmark={boolean} />` — N-mark in the existing indigo gradient (`linear-gradient(135deg, #6366F1, #818CF8)`), wordmark text "Narro" colored `#EDEDEF`. Message keys `common.nav.series`, `common.nav.episodes`, `common.nav.youtube`, `common.nav.billing`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/logo.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import Logo from "@/components/Logo";

describe("Logo", () => {
  it("renders the Narro wordmark by default", () => {
    render(<Logo />);
    expect(screen.getByText("Narro")).toBeInTheDocument();
    expect(screen.getByText("N")).toBeInTheDocument();
  });

  it("hides the wordmark when withWordmark is false", () => {
    render(<Logo withWordmark={false} />);
    expect(screen.queryByText("Narro")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- logo`
Expected: FAIL — module not found

- [ ] **Step 3: Build the Logo component and icon**

`frontend/src/components/Logo.tsx`:

```tsx
interface Props {
  size?: number;
  withWordmark?: boolean;
}

export default function Logo({ size = 32, withWordmark = true }: Props) {
  return (
    <span className="flex items-center gap-2">
      <span
        className="rounded-lg flex items-center justify-center font-bold text-white flex-shrink-0"
        style={{
          width: size,
          height: size,
          fontSize: size * 0.45,
          background: "linear-gradient(135deg, #6366F1, #818CF8)",
          boxShadow: "0 0 14px rgba(99,102,241,0.35)",
        }}
      >
        N
      </span>
      {withWordmark && (
        <span className="font-semibold" style={{ color: "#EDEDEF", fontSize: size * 0.5 }}>
          Narro
        </span>
      )}
    </span>
  );
}
```

`frontend/src/app/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#6366F1"/>
      <stop offset="1" stop-color="#818CF8"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <text x="32" y="44" font-family="Arial, sans-serif" font-size="34" font-weight="bold" fill="#fff" text-anchor="middle">N</text>
</svg>
```

Delete `frontend/src/app/favicon.ico` (the svg icon replaces it): `git rm src/app/favicon.ico`.

- [ ] **Step 4: Replace branding in chrome**

- `[locale]/dashboard/layout.tsx`: replace the "W / What If?" logo block with `<Logo size={32} />` (import it); NAV labels become `t("nav.series")` etc. — add `"nav": { "series": "Series", "episodes": "Episodes", "youtube": "YouTube", "billing": "Billing" }` under `common` in `en.json` and `"nav": { "series": "Series", "episodes": "Tập video", "youtube": "YouTube", "billing": "Thanh toán" }` in `vi.json`; the component gains `const t = useTranslations("common");`. Sign out button text → `t("logout")`.
- `[locale]/(auth)/layout.tsx`: replace any "What If?" mark with `<Logo size={36} />`.
- `components/landing/Nav.tsx` and `Footer.tsx`: swap ONLY the logo/name elements for `<Logo />` (copy rewrite happens in Task 4).

- [ ] **Step 5: Run tests + grep gate**

Run: `npm test`
Run: `grep -rn "What If?" src/ --include="*.tsx"` — remaining matches must be ONLY in landing copy files that Task 4 rewrites (list them in your report) and user-content placeholder text (e.g. episode title example "What if the internet…"). Zero matches in layouts/auth.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src frontend/messages
git commit -m "feat(brand): Narro logo component, icon, and chrome rebrand"
```

---

### Task 3: LocaleSwitcher in landing nav + dashboard sidebar

**Files:**
- Create: `frontend/src/components/LocaleSwitcher.tsx`
- Modify: `frontend/src/components/landing/Nav.tsx`, `frontend/src/app/[locale]/dashboard/layout.tsx`
- Test: `frontend/src/__tests__/locale-switcher.test.tsx`

**Interfaces:**
- Consumes: `usePathname`, `useRouter` from `@/i18n/navigation`; `useLocale` from `next-intl`.
- Produces: `<LocaleSwitcher />` — two-button EN | VI pill; clicking the inactive locale calls `router.replace(pathname, { locale })`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/locale-switcher.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LocaleSwitcher from "@/components/LocaleSwitcher";

const mockReplace = jest.fn();
jest.mock("@/i18n/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace: mockReplace }),
}));

beforeEach(() => jest.clearAllMocks());

describe("LocaleSwitcher", () => {
  it("renders EN and VI options", () => {
    render(<LocaleSwitcher />);
    expect(screen.getByRole("button", { name: "EN" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "VI" })).toBeInTheDocument();
  });

  it("switches to vi keeping the current path", async () => {
    const user = userEvent.setup();
    render(<LocaleSwitcher />);
    await user.click(screen.getByRole("button", { name: "VI" }));
    expect(mockReplace).toHaveBeenCalledWith("/dashboard", { locale: "vi" });
  });
});
```

Note: this file-level mock overrides the global setup mock — that is fine.

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- locale-switcher`
Expected: FAIL — module not found

- [ ] **Step 3: Build the component**

`frontend/src/components/LocaleSwitcher.tsx`:

```tsx
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
          {l}
        </button>
      ))}
    </span>
  );
}
```

- [ ] **Step 4: Mount it**

- `components/landing/Nav.tsx`: add `<LocaleSwitcher />` between the nav links and the Login button.
- `[locale]/dashboard/layout.tsx`: add `<LocaleSwitcher />` in the sidebar bottom section, above the Sign out button.

- [ ] **Step 5: Run tests, commit**

Run: `npm test`

```bash
git add -A frontend/src
git commit -m "feat(i18n): locale switcher in landing nav and dashboard sidebar"
```

---

### Task 4: Landing rewrite — copy + i18n for all 7 sections

**Files:**
- Modify: `frontend/src/components/landing/Nav.tsx`, `Hero.tsx`, `Features.tsx`, `HowItWorks.tsx`, `Pricing.tsx`, `CTA.tsx`, `Footer.tsx`; `frontend/messages/en.json`, `frontend/messages/vi.json`
- Test: `frontend/src/__tests__/landing.test.tsx`

**Interfaces:**
- Consumes: `useTranslations` (client components — every landing component already is or becomes `"use client"`), `Logo`, `LocaleSwitcher`, `Link` from `@/i18n/navigation`.
- Produces: message namespace `landing` (keys below). Visual style (dark indigo, blobs, animations) is KEPT — only text nodes and section structure change.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/landing.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import Hero from "@/components/landing/Hero";
import HowItWorks from "@/components/landing/HowItWorks";
import Features from "@/components/landing/Features";

describe("Landing copy (EN via mocked useTranslations)", () => {
  it("hero sells the series positioning, not generic AI video", () => {
    render(<Hero />);
    expect(screen.getByText("Turn one idea into a whole series")).toBeInTheDocument();
    expect(screen.getByText(/from our pilot episode/i)).toBeInTheDocument();
    expect(screen.queryByText(/editing skills/i)).not.toBeInTheDocument();
  });

  it("how-it-works shows the real 4-step pipeline", () => {
    render(<HowItWorks />);
    expect(screen.getByText(/Drop in your idea/i)).toBeInTheDocument();
    expect(screen.getByText(/AI writes the script — you approve it/i)).toBeInTheDocument();
  });

  it("features never promise a timeline editor", () => {
    render(<Features />);
    expect(screen.queryByText(/timeline/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Series asset library/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- landing`
Expected: FAIL — current copy doesn't match

- [ ] **Step 3: Add the `landing` namespace to both catalogs**

Append to `frontend/messages/en.json` (inside the root object):

```json
"landing": {
  "nav": { "features": "Features", "how": "How it works", "pricing": "Pricing", "cta": "Get started" },
  "hero": {
    "badge": "AI video agent for storytellers",
    "title": "Turn one idea into a whole series",
    "subtitle": "AI writes the script, you approve every word. Narro builds the video — consistent characters, voice, and style across every episode — and publishes straight to YouTube.",
    "cta": "Start your series",
    "ctaSecondary": "See how it works",
    "stats": [
      { "value": "1 idea", "label": "becomes an 8-minute script" },
      { "value": "34/37", "label": "scenes auto-matched to your assets" },
      { "value": "VI + EN", "label": "narration languages" }
    ],
    "statsNote": "from our pilot episode"
  },
  "how": {
    "title": "From idea to published episode",
    "steps": [
      { "title": "Drop in your idea", "body": "A rough premise and a target length are enough. Or paste a finished script." },
      { "title": "AI writes the script — you approve it", "body": "Narro drafts narration sized to your target duration. Edit every word before anything is produced." },
      { "title": "Scenes and images, matched automatically", "body": "The script is split into scenes, matched against your series asset library, and missing images are generated in your series style." },
      { "title": "Video out, straight to YouTube", "body": "Voice-over, subtitles, motion and music — rendered server-side and published to your channel in one click." }
    ]
  },
  "features": {
    "title": "Built for series, not one-off clips",
    "items": [
      { "title": "Script-to-length AI", "body": "Tell it 8 minutes, get an 8-minute script — in your series' language and tone." },
      { "title": "Series asset library", "body": "Characters, locations and props live at the series level, so episode 10 looks like episode 1." },
      { "title": "On-brand image generation", "body": "Missing scene images are generated from your series style bible — no prompt engineering." },
      { "title": "Multi-language narration", "body": "Vietnamese and English text-to-speech with a fixed voice per series." },
      { "title": "Subtitles that never mishear", "body": "Captions come from your script, not speech recognition — 100% accurate." },
      { "title": "One-click YouTube publish", "body": "Connect your channel once; every built episode uploads with title, description and tags." }
    ]
  },
  "cta": {
    "title": "Your first episode is one idea away",
    "body": "Start free, keep every video you make.",
    "button": "Start your series"
  },
  "footer": { "tagline": "The AI video agent for storytellers.", "rights": "All rights reserved." }
}
```

Append to `frontend/messages/vi.json`:

```json
"landing": {
  "nav": { "features": "Tính năng", "how": "Cách hoạt động", "pricing": "Bảng giá", "cta": "Bắt đầu" },
  "hero": {
    "badge": "Agent AI làm video cho người kể chuyện",
    "title": "Biến một ý tưởng thành cả series video",
    "subtitle": "AI viết kịch bản, bạn duyệt từng chữ. Narro dựng video — nhân vật, giọng đọc, phong cách nhất quán xuyên mọi tập — và đăng thẳng lên YouTube.",
    "cta": "Bắt đầu series của bạn",
    "ctaSecondary": "Xem cách hoạt động",
    "stats": [
      { "value": "1 ý tưởng", "label": "thành kịch bản 8 phút" },
      { "value": "34/37", "label": "cảnh tự khớp ảnh có sẵn" },
      { "value": "VI + EN", "label": "ngôn ngữ giọng đọc" }
    ],
    "statsNote": "từ tập thí điểm của chúng tôi"
  },
  "how": {
    "title": "Từ ý tưởng đến tập video đã đăng",
    "steps": [
      { "title": "Đưa ý tưởng vào", "body": "Một tiền đề sơ sài và thời lượng mong muốn là đủ. Hoặc dán kịch bản có sẵn." },
      { "title": "AI viết kịch bản — bạn duyệt", "body": "Narro viết lời dẫn đúng thời lượng bạn cần. Sửa từng chữ trước khi bất cứ thứ gì được sản xuất." },
      { "title": "Cảnh và ảnh, tự khớp", "body": "Kịch bản được chia cảnh, khớp với kho ảnh của series, ảnh thiếu được sinh đúng phong cách series." },
      { "title": "Video hoàn chỉnh, lên thẳng YouTube", "body": "Giọng đọc, phụ đề, chuyển động và nhạc — render trên server và đăng lên kênh của bạn trong một cú bấm." }
    ]
  },
  "features": {
    "title": "Sinh ra cho series, không phải clip lẻ",
    "items": [
      { "title": "AI viết đúng thời lượng", "body": "Yêu cầu 8 phút, nhận kịch bản 8 phút — đúng ngôn ngữ và giọng văn của series." },
      { "title": "Kho tài sản series", "body": "Nhân vật, bối cảnh, đồ vật nằm ở cấp series — tập 10 trông y như tập 1." },
      { "title": "Sinh ảnh đúng phong cách", "body": "Ảnh thiếu được sinh theo style bible của series — không cần biết viết prompt." },
      { "title": "Giọng đọc đa ngôn ngữ", "body": "TTS tiếng Việt và tiếng Anh, giọng cố định theo từng series." },
      { "title": "Phụ đề không bao giờ nghe nhầm", "body": "Phụ đề lấy từ kịch bản, không phải nhận dạng giọng nói — chính xác 100%." },
      { "title": "Đăng YouTube một cú bấm", "body": "Kết nối kênh một lần; mỗi tập build xong tự đăng kèm tiêu đề, mô tả, tag." }
    ]
  },
  "cta": {
    "title": "Tập đầu tiên chỉ cách bạn một ý tưởng",
    "body": "Bắt đầu miễn phí, giữ mọi video bạn làm ra.",
    "button": "Bắt đầu series của bạn"
  },
  "footer": { "tagline": "Agent AI làm video cho người kể chuyện.", "rights": "Bảo lưu mọi quyền." }
}
```

- [ ] **Step 4: Rewrite the components**

For each landing component: keep the existing visual wrappers (background, blobs, animation classNames, spacing) and REPLACE text nodes with `t(...)` lookups. Pattern (Hero shown; apply the same mechanics to the others):

```tsx
"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

export default function Hero() {
  const t = useTranslations("landing.hero");
  const stats = [0, 1, 2].map((i) => ({
    value: t(`stats.${i}.value`),
    label: t(`stats.${i}.label`),
  }));

  return (
    /* keep existing section wrapper + blob divs exactly as they are */
    /* badge text -> {t("badge")} */
    /* h1 -> {t("title")}, sub -> {t("subtitle")} */
    /* primary CTA -> <Link href="/signup">{t("cta")}</Link> */
    /* secondary CTA -> <a href="#how">{t("ctaSecondary")}</a> */
    /* stats row -> stats.map(...) plus a small muted note {t("statsNote")} under the row */
  );
}
```

Concrete requirements per component:
- **Nav**: links Features → `#features`, How it works → `#how`, Pricing → `#pricing` with `t("landing.nav.*")`; Login/Get started via `Link` to `/login` / `/signup`; `<Logo />` + `<LocaleSwitcher />` already present from Tasks 2-3.
- **Hero**: replace the old STATS array (`10× / 100% / 0 editing skills`) with the three pilot stats + `statsNote` — the old claims must be gone.
- **HowItWorks**: exactly 4 steps from `landing.how.steps` (numbered 1-4), section `id="how"`.
- **Features**: exactly 6 cards from `landing.features.items`, section `id="features"`; delete any card copy mentioning automatic script/scene magic without review, and anything about editing/timeline.
- **Pricing**: keep the current plan cards/logic; wrap the section heading and any static strings in `t()` — add whatever keys you need under `landing.pricing.*` in BOTH catalogs (e.g. `title`, `subtitle`, `perMonth`, `cta`) matching the strings currently hardcoded.
- **CTA / Footer**: swap copy to the keys above; footer shows `<Logo size={24} />`, `t("landing.footer.tagline")`, `© {year} Narro. {t("landing.footer.rights")}`.

- [ ] **Step 5: Run tests + grep gates**

Run: `npm test`
Run: `grep -rn "What If" src/components/landing/` → 0 matches.
Run: `grep -rn "AI-powered\|Editing skills\|10×" src/components/landing/` → 0 matches.
Manual: `npm run dev`, view `/en` and `/vi` — all seven sections read correctly in both languages.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src frontend/messages
git commit -m "feat(landing): Narro series-first copy in EN and VI"
```

---

### Task 5: Dashboard + auth string migration to catalogs

**Files:**
- Modify: `frontend/src/app/[locale]/(auth)/login/page.tsx`, `signup/page.tsx`; `[locale]/dashboard/page.tsx`, `episodes/new/page.tsx`, `episodes/[id]/page.tsx`, `series/page.tsx`, `series/[id]/page.tsx`, `youtube/page.tsx`, `billing/page.tsx`; `frontend/src/components/episode/ScriptPanel.tsx`; `frontend/messages/en.json`, `frontend/messages/vi.json`
- Test: extend `frontend/src/__tests__/i18n-routing.test.tsx` (the key-parity test already guards catalog drift)

**Interfaces:**
- Produces: namespaces `dashboard` (episode list, statuses), `episodes` (new/detail incl. build stages, script panel, generate-asset errors), `series` (list/detail/forms), `youtube`, `billing`. Error-code map moves INTO the catalogs: keys `errors.ERR_SCRIPT_GENERATION_FAILED`, `errors.ERR_SCRIPT_ANALYSIS_FAILED`, `errors.ERR_EPISODE_NOT_DRAFT`, `errors.ERR_IMAGE_GENERATION_FAILED`, `errors.ERR_NO_SERIES`, `errors.ERR_NO_ASSET_BRIEF`, `errors.ERR_YOUTUBE_NOT_CONNECTED`, `errors.ERR_EPISODE_NOT_BUILT`, plus `errors.generic`.

- [ ] **Step 1: Define the catalogs**

Extend BOTH message files with the namespaces below (EN shown; provide natural VI equivalents for every key — the parity test enforces completeness):

```json
"errors": {
  "generic": "Something went wrong — please try again.",
  "ERR_SCRIPT_GENERATION_FAILED": "Script generation failed — please try again.",
  "ERR_SCRIPT_ANALYSIS_FAILED": "Scene analysis failed — please try again.",
  "ERR_EPISODE_NOT_DRAFT": "Scenes can only be regenerated while the episode is a draft.",
  "ERR_IMAGE_GENERATION_FAILED": "Image generation failed — try again or upload manually.",
  "ERR_NO_SERIES": "This episode has no series — link it to a series to generate images.",
  "ERR_NO_ASSET_BRIEF": "This scene has no missing-image description to generate from.",
  "ERR_YOUTUBE_NOT_CONNECTED": "YouTube not connected. Go to Settings → YouTube first.",
  "ERR_EPISODE_NOT_BUILT": "Build the episode before publishing."
},
"dashboard": {
  "title": "Episodes", "empty": "No episodes yet.", "newEpisode": "New episode",
  "status": { "draft": "Draft", "building": "Building…", "built": "Built", "uploading": "Uploading…", "uploaded": "Published" }
},
"episodes": {
  "scenesTitle": "Scenes — upload an asset image for each",
  "assetReady": "Asset ready", "uploadAsset": "Upload asset", "replaceAsset": "Replace asset",
  "generateImage": "Generate image", "missingImage": "Missing image: {brief}",
  "buildTitle": "Build video", "buildHint": "All scenes need an uploaded asset before building.",
  "buildButton": "Build episode", "building": "Building…",
  "rebuildConfirm": "This episode is already built. Rebuilding re-runs voice-over for every scene and costs TTS credits. Continue?",
  "stageTts": "Voice-over {count}", "stageRender": "Rendering scenes {count}", "stageAssemble": "Assembling final video…", "stageWorking": "Working…",
  "lastBuildFailed": "Last build failed: {error}", "retryBuild": "Retry build",
  "downloadOutput": "Download output video",
  "publishTitle": "Publish to YouTube", "publishButton": "Publish to YouTube", "published": "Episode published to YouTube.", "viewOnYouTube": "View on YouTube",
  "script": { "title": "Script", "briefPlaceholder": "Episode idea / brief — a rough idea or a partial script", "targetMinutes": "Target minutes", "generate": "Generate script", "generating": "Generating…", "scriptPlaceholder": "The full narration script appears here — edit freely before splitting into scenes. You can also paste a finished script directly.", "split": "Split into scenes", "splitting": "Splitting…", "splitHint": "Splitting replaces the current scene list and matches each scene to your series assets.", "briefRequired": "Enter an episode idea first.", "scriptRequired": "Write or generate a script first." },
  "new": { "title": "New episode", "seriesLabel": "Series", "noSeries": "No series (standalone)", "titleLabel": "Title", "create": "Create episode", "addScene": "Add scene", "scenesCount": "Scenes ({count})", "narrationRequired": "All scenes need narration text." }
},
"series": {
  "title": "Series", "new": "New series", "create": "Create", "namePlaceholder": "Series name", "descriptionPlaceholder": "Description",
  "language": "Language", "styleBiblePlaceholder": "Style bible — describe the visual style used for every generated image (e.g. 'black stick figures on white background, minimal, bold red accents')",
  "voicePlaceholder": "TTS voice ID (e.g. ElevenLabs voice id — pick after the voice comparison)",
  "episodeCount": "{count} episodes", "empty": "No series yet. A series holds shared character images, style, and voice for all its episodes.",
  "assetsTitle": "Shared assets ({count})", "assetName": "Asset name (e.g. main_character)", "assetDescription": "Description — what is in this image (the AI matches scenes by this)",
  "uploadImage": "Upload image", "uploading": "Uploading…", "episodesTitle": "Episodes", "noEpisodes": "No episodes yet.", "newEpisode": "New episode", "nameRequired": "Series name is required.", "backToAll": "All series"
},
"youtube": { "title": "YouTube" },
"billing": { "title": "Billing" }
```

For `youtube`/`billing`, migrate the page headings and the most visible button/status strings you find in those files; add keys as needed (keep names descriptive, both locales).

- [ ] **Step 2: Migrate the components**

Mechanics per file: add `const t = useTranslations("<namespace>");`, replace string literals with `t("key")` / `t("key", {count, brief, error})`. Specific requirements:
- `episodes/[id]/page.tsx`: `STATUS_CONFIG` labels → `t("dashboard.status.*")` (move the map inside the component); `GENERATE_ASSET_ERRORS` map and ScriptPanel's `ERROR_MESSAGES` are DELETED — both replaced by `t(\`errors.${err.detail}\`)` with fallback: if the key equals the returned string (missing), show `err.detail` for unknown `ERR_` codes; `stageLabel()` uses the `stage*` keys.
- `ScriptPanel.tsx`: all strings via `episodes.script.*`; error handling via the shared `errors.*` lookup.
- Both auth pages: `auth.*` keys from Task 1.
- Update existing Jest tests' expected strings ONLY where a literal changed spelling; prefer keeping catalog values identical to the current English strings so most assertions survive unchanged.

- [ ] **Step 3: Run tests**

Run: `npm test` — all suites green (the i18n-routing parity test proves VI covers every new key).

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src frontend/messages
git commit -m "feat(i18n): migrate dashboard, episodes, series and auth strings to catalogs"
```

---

### Task 6: E2E + build gate — Playwright, lint cleanup, full verification

**Files:**
- Modify: `frontend/e2e/*.spec.ts` (whatever exists under the Playwright test dir — locate with `ls frontend; cat frontend/playwright.config.ts` for `testDir`), `frontend/src/__tests__/dashboard.test.tsx` + `new-episode.test.tsx` (pre-existing unused-var lint errors), `frontend/src/app/[locale]/dashboard/episodes/[id]/page.tsx` (exhaustive-deps warning if it blocks build)
- Test: this task IS the test.

- [ ] **Step 1: Fix the pre-existing lint errors that block `next build`**

Run `npx next lint` and fix exactly the reported errors: remove the unused `removeButtons` variable in `new-episode.test.tsx` (dead code at the old line 85 area) and any unused vars in `dashboard.test.tsx`; for the `react-hooks/exhaustive-deps` warning on the polling effect, add the missing dep or an inline `// eslint-disable-next-line react-hooks/exhaustive-deps` with a one-line reason. Do not fix unrelated warnings.

- [ ] **Step 2: Update Playwright specs**

Locale routing changed every URL: `page.goto("/")` now lands on `/en`. Update specs: expected URLs get the `/en` prefix; selectors matching "What If?" text change to "Narro"; login/signup flows unchanged otherwise. If a spec navigates to `/dashboard`, point it at `/en/dashboard`.

- [ ] **Step 3: Full verification**

Run: `npm test` → all green.
Run: `npm run build` → succeeds INCLUDING lint.
Run: `npm run test:e2e` → green (requires backend + docker running: start per SETUP.md if needed).
Run: `grep -ri "what if" src/ --include="*.tsx" | grep -v -i "what if the internet"` → only user-content placeholders remain (report the exact list).

- [ ] **Step 4: Commit**

```bash
git add -A frontend
git commit -m "test(e2e): locale-aware Playwright specs, lint cleanup, Narro build gate"
```

---

## Self-review notes (spec coverage)

- Rebrand: Tasks 2 (chrome + icon) + 4 (landing) + 6 (grep gate). ✅
- i18n next-intl `/en` `/vi` + switcher + catalogs: Tasks 1, 3, 5. ✅
- Landing 7 sections, honest copy, pilot stats: Task 4. ✅
- Error-map i18n (spec "Xử lý lỗi"): Task 5 `errors.*`. ✅
- Playwright same-wave update (spec: "không để test đỏ qua đêm"): Task 6. ✅
- Wave 2 items (wizard, settings, voice picker, PUT /series, preferences): intentionally absent. ✅
