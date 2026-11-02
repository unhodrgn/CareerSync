import type { ReactNode } from 'react'
export function Icon({ name, size = 20 }: {
  name: string
  size?: number
}) {
  const paths: Record<string, ReactNode> = {
    search: <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 5 5" />
    </>, arrow: <path d="M4 12h16m-6-6 6 6-6 6" />, pin: <>
      <path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" />
      <circle cx="12" cy="10" r="2" />
    </>, bookmark: <path d="M6 3h12v18l-6-4-6 4Z" />, check: <path d="m5 12 4 4L19 6" />, upload: <>
      <path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" />
    </>, grid: <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || <>
    <path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z" />
  </>}</svg>
}
