import { useLocation } from 'react-router';
import { errorCode } from '@/api/errors';
import { aiConsentWithdrawn, consentPath, useAuth } from '@/auth/AuthContext';
import { Blocked, ErrorPanel } from '@/components/common/States';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';

export interface GateCopy {
  title: string;
  body: string;
  action: string;
}

/**
 * A failed seeker AI request. The two 409s that mean "a precondition is missing" get a panel with the way to fix
 * it: `AI_CONSENT_REQUIRED` (consent withdrawn or given to an older text, D16, D17) → the consent page, and
 * `CV_NOT_CONFIRMED` → 내 이력서. Anything else is an error with 다시 시도.
 */
export default function SeekerGate({
  error,
  onRetry,
  noCv,
  consent,
}: {
  error: unknown;
  onRetry?: () => void;
  noCv?: GateCopy;
  consent?: GateCopy;
}) {
  const { user } = useAuth();
  const location = useLocation();
  const code = errorCode(error);

  if (code === 'AI_CONSENT_REQUIRED') {
    const withdrawn = user ? aiConsentWithdrawn(user) : false;
    const copy = consent ?? {
      title: t('blocked.consent.title'),
      body: t(withdrawn ? 'blocked.consent.bodyWithdrawn' : 'blocked.consent.bodyUpdated'),
      action: t('blocked.consent.action'),
    };
    return <Blocked {...copy} to={consentPath(`${location.pathname}${location.search}`)} />;
  }
  if (code === 'CV_NOT_CONFIRMED' || code === 'CV_NOT_FOUND') {
    const copy = noCv ?? { title: t('blocked.noCv.title'), body: t('blocked.noCv.body'), action: t('blocked.noCv.action') };
    return <Blocked {...copy} to={paths.seeker.cv} />;
  }
  return <ErrorPanel error={error} onRetry={onRetry} />;
}
