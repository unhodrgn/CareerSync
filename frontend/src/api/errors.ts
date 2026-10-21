import { t, type MessageKey } from '@/i18n';
import { ApiError } from './client';

/** Backend `AppError` codes the UI explains in its own words; anything else gets the generic message. */
const CODE_TEXT: Partial<Record<string, MessageKey>> = {
  NETWORK: 'error.network',
  VALIDATION: 'error.validation',
  SEEKER_ONLY: 'error.seekerOnly',
  JOB_NOT_FOUND: 'error.jobNotFound',
  JOB_EXPIRED: 'error.jobExpired',
  COMPANY_NOT_FOUND: 'error.companyNotFound',
  ALREADY_APPLIED: 'error.alreadyApplied',
  AI_CONSENT_REQUIRED: 'error.aiConsentRequired',
  CV_NOT_CONFIRMED: 'error.cvNotConfirmed',
  CV_NOT_FOUND: 'error.cvNotFound',
  CV_TOO_LARGE: 'error.cvTooLarge',
  CV_NOT_PDF: 'error.cvNotPdf',
  CV_UNREADABLE: 'error.cvUnreadable',
  CV_ENCRYPTED: 'error.cvEncrypted',
  CV_TOO_MANY_PAGES: 'error.cvTooManyPages',
  CV_NO_TEXT: 'error.cvNoText',
  OFFER_NOT_FOUND: 'error.offerNotFound',
  OFFER_NOT_PENDING: 'error.offerNotPending',
  OFFER_EXPIRED: 'error.offerExpired',
  // Company pages
  DEADLINE_IN_PAST: 'error.deadlineInPast',
  FIELD_REQUIRED: 'error.fieldRequired',
  JOB_CLOSED: 'error.jobClosed',
  JOB_FIELD_LOCKED: 'error.jobFieldLocked',
  JOB_NOT_DRAFT: 'error.jobNotDraft',
  JOB_NOT_PUBLISHED: 'error.jobNotPublished',
  JOB_INCOMPLETE: 'error.jobIncomplete',
  CRITERIA_COUNT_INVALID: 'error.criteriaCount',
  CRITERIA_DUPLICATE_NAME: 'error.criteriaDuplicate',
  WEIGHT_SUM_INVALID: 'error.weightSum',
  CRITERIA_MAJOR_REQUIRED: 'error.criteriaMajor',
  CRITERIA_BLOCKED: 'error.criteriaBlocked',
  CRITERIA_LOCKED: 'error.criteriaLocked',
  APPLICATION_NOT_FOUND: 'error.applicationNotFound',
  EVALUATION_DONE: 'error.evaluationDone',
  EVALUATION_IN_PROGRESS: 'error.evaluationInProgress',
  AI_CONSENT_WITHDRAWN: 'error.aiConsentWithdrawn',
  TALENT_NOT_FOUND: 'error.talentNotFound',
  OFFER_EXISTS: 'error.offerExists',
  OFFER_REJECTED: 'error.offerRejected',
  OFFER_DAILY_LIMIT: 'error.offerDailyLimit',
  PROJECT_NOT_FOUND: 'error.projectNotFound',
  PROJECT_LIMIT: 'error.projectLimit',
};

/** The `code` of a failed request, or null for anything that is not an ApiError. */
export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.code : null;
}

/** One Korean sentence for a failed request. */
export function errorText(error: unknown): string {
  const key = error instanceof ApiError ? CODE_TEXT[error.code] : undefined;
  return t(key ?? 'error.server');
}
