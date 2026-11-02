import { MATCH_DISCLAIMER } from '../services/matchView'
import type { MatchLevel } from '../types/recommendation'

/** A match score with its band, always with the disclaimer and the AI notice beside it (D42). */
export function MatchScore({ score, level, notice }: { score: number, level: MatchLevel, notice: string }) {
  return <div className="match-score">
    <span>매칭 점수</span>
    <b>{score}<small>점</small></b>
    <span className="status match-level">{level}</span>
    <span>{MATCH_DISCLAIMER}</span>
    <span className="ai-notice">{notice}</span>
  </div>
}
