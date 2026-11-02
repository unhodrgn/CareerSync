// What the match-score parts of the pages show (D42–D44). The score itself comes from the backend; nothing here
// computes or guesses one.
import type { Page } from '../types'
import type { Role } from '../types/common'
import type { JobMatch } from '../types/recommendation'

/** Shown next to every match score (D42). */
export const MATCH_DISCLAIMER = '점수는 합격 가능성을 뜻하지 않습니다.'

/**
 * What the job detail page shows for the match score: nothing for guests, companies and applied jobs (D44) or while
 * the answer is loading; otherwise the status GET /api/jobs/{id}/match returned.
 */
export function detailMatchState(role: Role | null, applied: boolean, match: JobMatch | null): 'hidden' | JobMatch['status'] {
  if (role !== 'seeker' || applied || !match)
    return 'hidden'
  if (match.status === 'done' && match.match_score === null)
    return 'none'
  return match.status
}

/** The next step for a refused GET /api/recommendations/jobs; the message itself comes from services/errors.ts. */
export const RECOMMENDATION_NEXT: Record<string, { label: string, page: Page } | undefined> = {
  CV_NOT_CONFIRMED: { label: '내 이력서 확인하러 가기 →', page: 'resume' },
  AI_CONSENT_REQUIRED: { label: 'AI 분석 동의하러 가기 →', page: 'consent' },
}
