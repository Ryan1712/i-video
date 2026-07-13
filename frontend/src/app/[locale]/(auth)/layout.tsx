import { Link } from "@/i18n/navigation";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: "#08080C" }}
    >
      {/* Top bar */}
      <div className="p-6">
        <Link href="/" className="flex items-center gap-2 w-fit">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold text-white"
            style={{
              background: "linear-gradient(135deg, #6366F1, #818CF8)",
              boxShadow: "0 0 16px rgba(99,102,241,0.4)",
            }}
          >
            W
          </div>
          <span className="font-semibold text-sm" style={{ color: "#EDEDEF" }}>
            What If<span style={{ color: "#818CF8" }}>?</span>
          </span>
        </Link>
      </div>

      {/* Center content */}
      <div className="flex-1 flex items-center justify-center px-6 pb-16">
        {children}
      </div>
    </div>
  );
}
