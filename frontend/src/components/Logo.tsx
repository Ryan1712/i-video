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
