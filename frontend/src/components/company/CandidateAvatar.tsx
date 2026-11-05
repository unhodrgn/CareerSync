import { useId, type ReactElement } from 'react';

// An abstract avatar for a candidate on the company side (DESIGN.md Candidate avatar): geometric shapes and design
// token colours only — no face, figure or anything that suggests gender, age or ethnicity. It is generated from a
// non-identifying seed (the talent `anonymous_id`, or "A-" + `application_id` for applicants), never from a name,
// email or other personal data, so the same seed always draws the same avatar. The two seeds are kept apart on
// purpose: matching avatars would link an anonymous talent profile to a named applicant.

/** FNV-1a, 32 bit: a stable hash of the seed. */
function hash(seed: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

/** mulberry32: a small deterministic stream of numbers in [0, 1) from the hash. */
function stream(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Background and two shape colours, all design tokens (CSS variables), picked so the shapes stay visible
const PALETTES: [string, string, string][] = [
  ['--ds-accent-wash', '--ds-accent-text', '--ds-ring'],
  ['--ds-match-from', '--ds-ring', '--ds-accent'],
  ['--ds-accent-soft', '--ds-match-to', '--ds-accent'],
  ['--ds-chip', '--ds-accent-text', '--ds-ring'],
  ['--ds-match-to', '--ds-accent', '--ds-accent-soft'],
  ['--ds-accent-wash', '--ds-match-to', '--ds-accent'],
];

const V = 40; // viewBox size

type Draw = (a: string, b: string, r: () => number) => ReactElement;

// Compositions on a 40 × 40 square, clipped to a circle
const LAYOUTS: Draw[] = [
  // A large circle off-centre and a small one
  (a, b, r) => (
    <>
      <circle cx={10 + r() * 20} cy={10 + r() * 20} r={13 + r() * 6} fill={a} />
      <circle cx={8 + r() * 24} cy={8 + r() * 24} r={4 + r() * 4} fill={b} />
    </>
  ),
  // A quarter circle from a corner and a turned square
  (a, b, r) => {
    const corner = Math.floor(r() * 4);
    const cx = corner % 2 ? V : 0;
    const cy = corner < 2 ? 0 : V;
    const s = 9 + r() * 5;
    return (
      <>
        <circle cx={cx} cy={cy} r={22 + r() * 8} fill={a} />
        <rect x={20 - s / 2} y={20 - s / 2} width={s} height={s} rx={2} fill={b} transform={`rotate(${Math.floor(r() * 4) * 22.5} 20 20)`} />
      </>
    );
  },
  // A diagonal band and a dot
  (a, b, r) => {
    const w = 10 + r() * 8;
    return (
      <>
        <rect x={-10} y={20 - w / 2} width={60} height={w} fill={a} transform={`rotate(${r() < 0.5 ? 45 : -45} 20 20)`} />
        <circle cx={10 + r() * 20} cy={10 + r() * 20} r={4 + r() * 3} fill={b} />
      </>
    );
  },
  // A 2 × 2 grid with two or three tiles filled
  (a, b, r) => {
    const tiles = [0, 1, 2, 3].filter(() => r() < 0.6);
    const shown = tiles.length >= 2 ? tiles : [0, 3];
    return (
      <>
        {shown.map((i) => (
          <rect key={i} x={6 + (i % 2) * 15} y={6 + Math.floor(i / 2) * 15} width={13} height={13} rx={3} fill={i === shown[0] ? b : a} />
        ))}
      </>
    );
  },
  // Concentric rings
  (a, b, r) => {
    const cx = 14 + r() * 12;
    const cy = 14 + r() * 12;
    return (
      <>
        <circle cx={cx} cy={cy} r={16} fill="none" stroke={a} strokeWidth={5} />
        <circle cx={cx} cy={cy} r={6 + r() * 2} fill={b} />
      </>
    );
  },
  // A half disc and a triangle
  (a, b, r) => {
    const top = r() < 0.5;
    return (
      <>
        <path d={top ? 'M0 22 A20 20 0 0 1 40 22 Z' : 'M0 18 A20 20 0 0 0 40 18 Z'} fill={a} />
        <path d={top ? 'M12 38 L20 24 L28 38 Z' : 'M12 2 L20 16 L28 2 Z'} fill={b} transform={`translate(${(r() - 0.5) * 12} 0)`} />
      </>
    );
  },
];

/** The candidate's abstract avatar; decorative (the visible ID or name next to it is the text). */
export default function CandidateAvatar({ seed, size = 40 }: { seed: string; size?: number }) {
  const clip = useId();
  const h = hash(seed);
  const r = stream(h);
  const [bg, a, b] = PALETTES[h % PALETTES.length].map((v) => `var(${v})`);
  const layout = LAYOUTS[Math.floor(h / PALETTES.length) % LAYOUTS.length];
  return (
    <svg
      viewBox={`0 0 ${V} ${V}`}
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      style={{ flex: 'none', display: 'block' }}
    >
      <clipPath id={clip}>
        <circle cx={20} cy={20} r={20} />
      </clipPath>
      <g clipPath={`url(#${clip})`}>
        <rect width={V} height={V} fill={bg} />
        {layout(a, b, r)}
      </g>
    </svg>
  );
}
