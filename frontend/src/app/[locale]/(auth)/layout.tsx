import { Link } from "@/i18n/navigation";
import Logo from "@/components/Logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: "#08080C" }}
    >
      {/* Top bar */}
      <div className="p-6">
        <Link href="/" className="w-fit">
          <Logo size={36} />
        </Link>
      </div>

      {/* Center content */}
      <div className="flex-1 flex items-center justify-center px-6 pb-16">
        {children}
      </div>
    </div>
  );
}
