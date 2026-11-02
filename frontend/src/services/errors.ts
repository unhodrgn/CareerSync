// One Korean sentence for any failed request. Texts come from the old frontend's ko.ts; moving them to t() from
// src/i18n is a separate task.
import { ApiError, issueText } from './httpClient'

/** Backend `AppError` codes (and client codes) the UI explains in its own words. */
const CODE_TEXT: Record<string, string> = {
  NETWORK: '서버에 연결할 수 없습니다. 네트워크를 확인한 뒤 다시 시도해 주세요.',
  SERVER: '일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.',
  HTTP_401: '로그인이 필요합니다.',
  EMAIL_TAKEN: '이미 가입된 이메일입니다.',
  INVALID_CREDENTIALS: '이메일 또는 비밀번호가 올바르지 않습니다.',
  CONSENT_VERSION_OUTDATED: '동의 문구가 방금 변경되었습니다. 바뀐 내용을 확인하고 다시 동의해 주세요.',
  SEEKER_ONLY: '구직자 계정에서만 쓸 수 있습니다.',
  NAME_LOCKED: '이력서를 올린 뒤에는 이름을 바꿀 수 없습니다. 이력서의 개인정보를 가릴 때 이 이름을 사용했기 때문입니다.',
  NAME_CHANGED: '분석하는 동안 이름이 바뀌었습니다. 이력서를 다시 올려 주세요.',
  JOB_NOT_FOUND: '공고를 찾을 수 없습니다. 마감되었거나 게시가 끝난 공고일 수 있습니다.',
  JOB_EXPIRED: '마감된 공고라 지원할 수 없습니다.',
  COMPANY_NOT_FOUND: '기업 정보를 찾을 수 없습니다.',
  ALREADY_APPLIED: '이미 지원한 공고입니다.',
  AI_CONSENT_REQUIRED: 'AI 분석 동의가 있어야 할 수 있습니다.',
  CV_NOT_CONFIRMED: '확인한 이력서가 없습니다. 내 이력서에서 내용을 확인하고 저장해 주세요.',
  CV_NOT_FOUND: '올린 이력서가 없습니다.',
  CV_TOO_LARGE: '이력서 파일은 5MB 이하여야 합니다.',
  CV_NOT_PDF: 'PDF 파일만 올릴 수 있습니다.',
  CV_UNREADABLE: 'PDF를 읽을 수 없습니다. 파일이 손상되지 않았는지 확인해 주세요.',
  CV_ENCRYPTED: '암호가 걸린 PDF는 읽을 수 없습니다. 암호를 풀고 다시 올려 주세요.',
  CV_TOO_MANY_PAGES: '이력서는 5쪽 이하여야 합니다.',
  CV_NO_TEXT: '글자를 읽을 수 없는 PDF입니다. 스캔한 이미지가 아닌 텍스트 PDF를 올려 주세요.',
  DEADLINE_IN_PAST: '마감일은 오늘 이후여야 합니다.',
  FIELD_REQUIRED: '비울 수 없는 항목이 있습니다.',
  JOB_CLOSED: '마감된 공고는 바꿀 수 없습니다.',
  JOB_FIELD_LOCKED: '게시한 공고는 마감일, 근무지, 급여 안내만 바꿀 수 있습니다.',
  JOB_NOT_DRAFT: '작성 중인 공고에서만 할 수 있습니다.',
  JOB_NOT_PUBLISHED: '게시 중인 공고만 마감할 수 있습니다.',
  JOB_INCOMPLETE: '공고 내용을 입력해야 게시할 수 있습니다.',
  APPLICATION_NOT_FOUND: '지원 내역을 찾을 수 없습니다.',
}

/** The `code` of a failed request, or null for anything that is not an ApiError. */
export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.code : null
}

/**
 * Known code → fixed text; a 422 → the first issue the backend wrote (Korean for its own validators);
 * otherwise the server's message when it sent one, else the generic text.
 */
export function errorText(error: unknown): string {
  if (!(error instanceof ApiError))
    return CODE_TEXT.SERVER
  if (CODE_TEXT[error.code])
    return CODE_TEXT[error.code]
  if (error.code === 'VALIDATION') {
    const issue = error.form[0] ?? Object.values(error.fields)[0]
    return issue ? issueText(issue) : '입력한 내용을 확인해 주세요.'
  }
  return error.message || CODE_TEXT.SERVER
}
