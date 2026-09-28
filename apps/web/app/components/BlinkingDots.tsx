// Three pulsing dots (keyframes `dot-blink` live in globals.css).
export function BlinkingDots({ color, gap }: { color: string; gap: string }) {
  return (
    <span style={{ display: "flex", gap }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: "50%",
            background: color,
            animation: "dot-blink 1.2s infinite",
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
    </span>
  );
}
