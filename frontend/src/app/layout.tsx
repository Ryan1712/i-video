// Root layout is a passthrough; <html> lives in [locale]/layout.tsx so the
// lang attribute matches the active locale.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
