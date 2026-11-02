// Consent items shown at registration and on the re-consent page (D17). Wording from the old frontend's ko.ts,
// still a draft there (`auth.consent.draftNote`).
export const consentItems = [
  {
    name: 'consent_privacy',
    title: '개인정보 수집·이용 동의',
    body: '수집 항목: 이메일, 비밀번호(암호화하여 저장), 이름, 기업 회원의 회사명, 구직자가 올린 이력서에서 추출한 정보.\n이용 목적: 회원 관리, 채용 공고 지원과 평가, 맞춤 공고 추천.\n보관 기간: 확정 예정.\n동의를 거부할 수 있으며, 거부하면 회원가입을 할 수 없습니다.',
  },
  {
    name: 'consent_ai',
    title: 'AI 분석 안내 동의',
    body: '이력서는 이름과 연락처 등 개인정보를 가린 뒤 AI가 분석합니다.\nAI 분석은 명시적으로 동의한 경우에만 진행되며, 지원 평가와 맞춤 공고 추천에 사용됩니다.\nAI 분석 결과는 참고용입니다. 합격과 불합격을 포함한 모든 채용 결정은 기업의 채용 담당자가 합니다.\n구직자는 언제든 AI 분석 동의를 철회할 수 있으며, 철회한 뒤에는 새로운 AI 분석이 진행되지 않습니다.',
  },
] as const

export const consentDraftNote = '확정 전 초안 문구입니다.'
