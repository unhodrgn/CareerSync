import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import { api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { AiBox, AiBusy, AiMark } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { formatDate } from '@/components/common/format';
import { CheckIcon, ChevronDownIcon, ChevronUpIcon, RefreshIcon } from '@/components/common/icons';
import { ApplicationStatusTag, CategoryTag, ScoreSquare } from '@/components/common/Labels';
import { cx } from '@/components/common/Page';
import { applicantExperience, GateDetail, hasGate } from '@/components/common/RequiredGate';
import { ErrorPanel, InlineError, Loading, Notice } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import CandidateAvatar from './CandidateAvatar';
import { t } from '@/i18n';
import type { ApplicantRow, ApplicationStatus } from '@/types/application';
import { CATEGORIES, type Category } from '@/types/criteria';
import s from './company.module.css';

const asCategory = (c: string): Category => (CATEGORIES.includes(c as Category) ? (c as Category) : 'other');

// Progress through the process, then the decisions; 합격 and 불합격 reach the seeker as an outcome, so they ask first
const PROGRESS: ApplicationStatus[] = ['submitted', 'reviewing', 'interview'];
const OUTCOME: ApplicationStatus[] = ['on_hold', 'passed', 'rejected'];
type Confirmable = 'passed' | 'rejected';
const needsConfirm = (x: ApplicationStatus): x is Confirmable => x === 'passed' || x === 'rejected';

/**
 * The panel is CSS sticky (top) with its natural height, so the page is the only scroll container. CSS cannot keep a
 * panel taller than the window in view both ways, so only then this moves the sticky top with the scroll, once per
 * frame: down until the panel's bottom is in view, up until its top is, and nothing in between. A panel that fits
 * is left to CSS. Listeners, the observer and any pending frame are removed when the panel goes away.
 */
function useStickyPanel(ref: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const BOTTOM_GAP = 16;
    const topGap = parseFloat(getComputedStyle(el).top) || 24;
    let frame = 0;
    let following = false;
    let lastY = window.scrollY;
    let prevTop = el.getBoundingClientRect().top;

    const update = () => {
      frame = 0;
      const y = window.scrollY;
      const minTop = Math.min(topGap, window.innerHeight - el.offsetHeight - BOTTOM_GAP);
      const next = Math.min(topGap, Math.max(minTop, prevTop - (y - lastY)));
      lastY = y;
      el.style.top = `${next}px`;
      prevTop = el.getBoundingClientRect().top;
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    const stop = () => {
      window.removeEventListener('scroll', onScroll);
      cancelAnimationFrame(frame);
      frame = 0;
      el.style.top = '';
      following = false;
    };
    // Re-checked whenever the panel or the window changes size (evaluation loaded, confirm opened, resize)
    const sync = () => {
      const tall = el.offsetHeight > window.innerHeight - topGap - BOTTOM_GAP;
      if (tall && !following) {
        lastY = window.scrollY;
        prevTop = el.getBoundingClientRect().top;
        window.addEventListener('scroll', onScroll, { passive: true });
        following = true;
      } else if (!tall && following) {
        stop();
      }
      if (following) onScroll();
    };
    const observer = new ResizeObserver(sync);
    observer.observe(el);
    window.addEventListener('resize', sync);
    sync();
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', sync);
      stop();
    };
  }, [ref]);
}

/** True while the element is outside the window (the observer is removed with the element). */
function useOutOfView(ref: RefObject<HTMLElement | null>) {
  const [out, setOut] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setOut(!entry.isIntersecting));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return out;
}

/** Where focus goes when this applicant opens: the heading (a row was chosen) or the prev/next button that was used. */
export interface DetailFocus {
  target: 'heading' | 'prev' | 'next';
  /** A new object per request, so choosing the same applicant again still moves focus. */
  n: number;
}

/**
 * The selected applicant: the per-criterion evaluation with its CV evidence first, then the status in a footer
 * pinned to the bottom of the window while the panel runs past it (the page is the only scroll container). Status changes only by the recruiter's click (AI rule 5): 합격 and 불합격
 * ask first, every change can be undone once, and nothing reverts on its own. Remounts per applicant, so the
 * undo ends when another applicant is chosen.
 */
export default function ApplicantDetail({
  row,
  criteriaCount,
  position,
  total,
  onPrev,
  onNext,
  focusRequest,
  onEscape,
  onStatusChanged,
  onEvaluationChanged,
}: {
  row: ApplicantRow;
  criteriaCount: number;
  /** 1-based place in the visible (ranked, filtered) list */
  position: number;
  total: number;
  onPrev?: () => void;
  onNext?: () => void;
  focusRequest: DetailFocus | null;
  /** Escape outside a confirm: back to this applicant's row */
  onEscape: () => void;
  onStatusChanged: (status: ApplicationStatus) => void;
  onEvaluationChanged: () => void;
}) {
  const evaluation = useApi(() => api.evaluation(row.application_id), [row.application_id, row.evaluation_status]);
  const headingId = useId();
  const statusTitleId = useId();
  const gateTitleId = useId();
  // The evaluation's full gate (D50) once it has loaded; the row's (the same server helper) meanwhile
  const gate = (evaluation.state.status === 'ok' ? evaluation.state.data.required_gate : undefined) ?? row.required_gate;
  const panelRef = useRef<HTMLElement>(null);
  useStickyPanel(panelRef);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingAway = useOutOfView(headingRef);
  const prevRef = useRef<HTMLButtonElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);

  const [busy, setBusy] = useState(false);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [confirm, setConfirm] = useState<Confirmable | null>(null);
  // The option that opened the confirm gets focus back on cancel; cleared on success so focus lands on the result
  const [trigger, setTrigger] = useState<ApplicationStatus | null>(null);
  const [result, setResult] = useState<{ kind: 'changed' | 'undone'; status: ApplicationStatus } | null>(null);
  const [undoTo, setUndoTo] = useState<ApplicationStatus | null>(null);
  const focus = useConfirmFocus<HTMLButtonElement, HTMLDivElement, HTMLDivElement>(confirm !== null);

  const [retryBusy, setRetryBusy] = useState(false);
  const [retryNote, setRetryNote] = useState<unknown>(null);
  const [retried, setRetried] = useState(false);

  useEffect(() => {
    if (!focusRequest) return;
    const wanted = focusRequest.target === 'prev' ? prevRef.current : focusRequest.target === 'next' ? nextRef.current : null;
    // At the first or last applicant that button is disabled: the heading takes focus and announces the name
    (wanted && !wanted.disabled ? wanted : headingRef.current)?.focus({ preventScroll: true });
  }, [focusRequest]);

  const apply = async (status: ApplicationStatus, mode: 'change' | 'undo') => {
    const previous = row.status;
    setBusy(true);
    setStatusError(null);
    try {
      const updated = await api.setApplicationStatus(row.application_id, status);
      onStatusChanged(updated.status);
      if (mode === 'undo') {
        setUndoTo(null);
        setResult({ kind: 'undone', status: updated.status });
        // The 되돌리기 button is gone: keep focus on the line that says what happened
        focus.fallbackRef.current?.focus();
      } else {
        setUndoTo(previous);
        setResult({ kind: 'changed', status: updated.status });
      }
      if (confirm) {
        setTrigger(null);
        setConfirm(null);
      }
    } catch (e) {
      setStatusError(e);
    } finally {
      setBusy(false);
    }
  };

  const choose = (status: ApplicationStatus) => {
    if (status === row.status || busy) return;
    if (needsConfirm(status)) {
      setStatusError(null);
      setTrigger(status);
      setConfirm(status);
    } else {
      void apply(status, 'change');
    }
  };

  const cancel = () => (setConfirm(null), setStatusError(null));

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== 'Escape') return;
    e.preventDefault();
    if (confirm) cancel();
    else onEscape();
  };

  const retry = async () => {
    setRetryBusy(true);
    setRetryNote(null);
    try {
      await api.retryEvaluation(row.application_id);
      setRetried(true);
      onEvaluationChanged();
    } catch (e) {
      setRetryNote(e);
      // Finished or running meanwhile: show the current state
      if (errorCode(e) === 'EVALUATION_DONE') onEvaluationChanged();
    } finally {
      setRetryBusy(false);
    }
  };

  const options = (labelKey: 'apl.detail.progress' | 'apl.detail.outcome', statuses: ApplicationStatus[]) => {
    const labelId = `${statusTitleId}-${labelKey}`;
    return (
      <div className={s.statusRow} role="group" aria-labelledby={labelId}>
        <span id={labelId} className={s.statusRowLabel}>
          {t(labelKey)}
        </span>
        {statuses.map((x) => (
          <button
            key={x}
            ref={x === trigger ? focus.triggerRef : undefined}
            type="button"
            className={s.statusOption}
            aria-pressed={row.status === x}
            disabled={busy}
            onClick={() => choose(x)}
          >
            {t(`appStatus.${x}`)}
          </button>
        ))}
      </div>
    );
  };

  return (
    <aside ref={panelRef} className={cx(s.detail, ui.reveal)} aria-labelledby={headingId} onKeyDown={onKeyDown}>
      <div className={s.detailNav} role="group" aria-label={t('apl.nav.label')}>
        <span className={s.navPosition}>{t('apl.nav.position', { n: position, total })}</span>
        {/* The heading says the name to assistive tech; this copy is only for the eye */}
        <span className={s.navName} data-shown={headingAway || undefined} aria-hidden="true">
          {row.name}
        </span>
        <button
          ref={prevRef}
          type="button"
          className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)}
          aria-label={t('apl.nav.prev')}
          title={t('apl.nav.prev')}
          disabled={!onPrev}
          onClick={onPrev}
        >
          <ChevronUpIcon width={18} height={18} />
        </button>
        <button
          ref={nextRef}
          type="button"
          className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)}
          aria-label={t('apl.nav.next')}
          title={t('apl.nav.next')}
          disabled={!onNext}
          onClick={onNext}
        >
          <ChevronDownIcon width={18} height={18} />
        </button>
      </div>

      <div className={s.detailBody}>
        <div className={s.detailHead}>
          <div className={s.person}>
            <CandidateAvatar seed={`A-${row.application_id}`} size={48} />
            <div className={s.personText}>
              <h2 id={headingId} ref={headingRef} tabIndex={-1} className={s.detailName}>
                {row.name}
              </h2>
              <p className={cx(ui.caption, s.truncate)} title={row.email}>
                {row.email}
              </p>
            </div>
          </div>
          {row.fit !== null && (
            <div className={s.fitBlock}>
              <span className={cx(ui.caption, s.aiHead)}>
                <AiMark size="sm" />
                {t('apl.col.fit')}
              </span>
              <span className={s.fitBig}>{row.fit.toFixed(1)}</span>
              <span className={cx(ui.caption, s.nowrap)}>{t('apl.detail.met', { total: criteriaCount, n: row.strong_count })}</span>
            </div>
          )}
        </div>
        {/* Full panel width, so it does not squeeze beside Fit */}
        <p className={cx(ui.caption, s.detailMeta)}>
          {t('apl.applied', { date: formatDate(row.applied_at) })}
          {row.evaluation_status === 'done' && ` · ${applicantExperience(row.experience_months, gate)}`}
        </p>

        {/* The required criteria gate (D50): its own section, before the criteria and apart from Fit. It needs no
            evaluation, so it shows while one is pending too; the label never changes the status pinned below */}
        {hasGate(gate) && (
          <section className={s.detailSection} aria-labelledby={gateTitleId}>
            <h3 id={gateTitleId} className={ui.sectionTitle}>
              {t('gate.title')}
            </h3>
            <GateDetail gate={gate} audience="company" />
          </section>
        )}

        <section className={s.detailSection} aria-labelledby="eval-title">
          <h3 id="eval-title" className={ui.sectionTitle}>
            {t('apl.detail.criteria')}
          </h3>

          {row.evaluation_status !== 'done' ? (
            <div className={ui.stack} style={{ gap: 10 }}>
              {row.evaluation_status === 'pending' ? <AiBusy>{t('apl.detail.pending')}</AiBusy> : <Notice>{t('apl.detail.failed')}</Notice>}
              {retried && !retryNote ? (
                <span className={ui.done} role="status">
                  <CheckIcon width={14} height={14} />
                  {t('apl.retrying')}
                </span>
              ) : (
                <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} style={{ justifySelf: 'start' }} disabled={retryBusy} onClick={retry}>
                  <RefreshIcon width={15} height={15} />
                  {t('apl.retry')}
                </button>
              )}
              {retryNote != null && <InlineError>{errorText(retryNote)}</InlineError>}
            </div>
          ) : evaluation.state.status === 'loading' ? (
            <Loading rows={5} panel={false} />
          ) : evaluation.state.status === 'error' ? (
            <ErrorPanel error={evaluation.state.error} onRetry={evaluation.reload} panel={false} />
          ) : (
            <AiBox>
              <AiNotice notice={evaluation.state.data.notice} method={evaluation.state.data.items[0]?.method} inBox />
              {evaluation.state.data.summary && <p className={ui.body}>{evaluation.state.data.summary}</p>}
              {evaluation.state.data.excluded_criteria.length > 0 && (
                <p className={ui.caption}>{t('apl.detail.excluded', { names: evaluation.state.data.excluded_criteria.map((c) => c.name).join(', ') })}</p>
              )}
              <div>
                {evaluation.state.data.items.map((item) => (
                  <div key={item.criterion_id} className={s.evalItem}>
                    <div className={s.evalHead}>
                      <span className={s.evalName}>
                        <ScoreSquare score={item.score} />
                        {item.name}
                      </span>
                      <span className={s.score}>{t('apl.detail.score', { n: item.score })}</span>
                    </div>
                    <span className={ui.listEnd} style={{ justifyContent: 'flex-start' }}>
                      <CategoryTag category={asCategory(item.category)} quiet />
                      <span className={ui.categoryText}>{t('apl.detail.weight', { n: Math.round(item.weight) })}</span>
                    </span>
                    {item.reason && (
                      <p className={ui.body} style={{ fontSize: 13.5 }}>
                        {item.reason}
                      </p>
                    )}
                    {item.evidence.length > 0 ? (
                      item.evidence.map((q, i) => (
                        <p key={i} className={ui.quote}>
                          {q}
                        </p>
                      ))
                    ) : (
                      <p className={ui.caption}>{t('apl.detail.noEvidence')}</p>
                    )}
                  </div>
                ))}
              </div>
            </AiBox>
          )}
        </section>
      </div>

      <section className={s.statusFoot} aria-labelledby={statusTitleId}>
        <div className={s.statusHead}>
          <h3 id={statusTitleId} className={s.statusTitle}>
            {t('apl.detail.status')}
          </h3>
          <ApplicationStatusTag status={row.status} />
        </div>

        {confirm ? (
          <div ref={focus.regionRef} tabIndex={-1} role="group" aria-label={t(`apl.detail.confirm.${confirm}`)} className={cx(ui.inlineConfirm, s.statusConfirm)}>
            <strong>{t(`apl.detail.confirm.${confirm}`)}</strong>
            <span className={s.statusConfirmBody}>{t('apl.detail.confirmBody')}</span>
            {statusError != null && <InlineError>{errorText(statusError)}</InlineError>}
            <div className={ui.actions}>
              <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} disabled={busy} onClick={() => apply(confirm, 'change')}>
                {t(`apl.detail.confirmDo.${confirm}`)}
              </button>
              <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} disabled={busy} onClick={cancel}>
                {t('common.cancel')}
              </button>
            </div>
          </div>
        ) : (
          <div className={s.statusGroups}>
            {options('apl.detail.progress', PROGRESS)}
            {options('apl.detail.outcome', OUTCOME)}
          </div>
        )}

        {/* Always present, so a change is announced; it takes focus after a confirmed change or an undo */}
        <div ref={focus.fallbackRef} tabIndex={-1} role="status" className={s.statusResult} hidden={confirm !== null}>
          {result ? (
            <>
              <span>{t(result.kind === 'undone' ? 'apl.detail.undone' : 'apl.detail.statusChanged', { status: t(`appStatus.${result.status}`) })}</span>
              {/* Stays after a failed request, so the undo can be tried again */}
              {undoTo && (
                <button type="button" className={cx(ui.btn, ui.quiet, ui.small, s.undo)} disabled={busy} onClick={() => apply(undoTo, 'undo')}>
                  {t('apl.detail.undo')}
                </button>
              )}
            </>
          ) : (
            <span className={ui.caption}>{t('apl.detail.statusNote')}</span>
          )}
        </div>
        {statusError != null && !confirm && <InlineError>{errorText(statusError)}</InlineError>}
      </section>
    </aside>
  );
}
