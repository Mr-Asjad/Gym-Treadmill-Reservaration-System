/* Small inline glyph set — currentColor, 20px box, round joins. Kept minimal on
   purpose so the app stays dependency-free. */
type P = { size?: number };
const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 20 20",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.9,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const Bolt = ({ size = 20 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="M11 2 4 11h5l-1 7 7-9h-5l1-7Z" fill="currentColor" stroke="none" />
  </svg>
);

export const Check = ({ size = 20 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="m4 10.5 4 4 8-9" />
  </svg>
);

export const Close = ({ size = 20 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="m5 5 10 10M15 5 5 15" />
  </svg>
);

export const ArrowRight = ({ size = 20 }: P) => (
  <svg {...base(size)} aria-hidden="true">
    <path d="M4 10h12M11 5l5 5-5 5" />
  </svg>
);
