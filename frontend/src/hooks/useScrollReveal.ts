import { useEffect, useRef } from 'react'

// Animation chỉ thuộc UI; không can thiệp state hay service/backend.
export function useScrollReveal(page: string, busy: boolean) {
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root || !('IntersectionObserver' in window)) return
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (preference.matches) return

    const targets = root.querySelectorAll<HTMLElement>(
      '.section-heading, .feature-banner, .job-card, .page-title, .panel, .partner-strip',
    )
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        entry.target.classList.add('is-revealed')
        observer.unobserve(entry.target)
      }
    }, { threshold: 0.08 })

    targets.forEach(element => {
      // Không animate lại phần đã hiển thị khi có request mới.
      if (element.classList.contains('is-revealed')) return
      const siblings = element.parentElement?.children
      const index = siblings ? Array.from(siblings).indexOf(element) : 0
      element.style.setProperty('--reveal-delay', `${Math.min(index, 3) * 70}ms`)
      element.classList.add('reveal-pending')
      observer.observe(element)
    })

    const showAll = () => targets.forEach(element => element.classList.add('is-revealed'))
    preference.addEventListener('change', showAll)
    return () => {
      observer.disconnect()
      preference.removeEventListener('change', showAll)
      targets.forEach(element => element.classList.remove('reveal-pending'))
    }
  }, [page, busy])

  return rootRef
}
