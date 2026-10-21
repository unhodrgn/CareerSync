import { Link } from 'react-router';
import { ArrowRightIcon } from '@/components/common/icons';
import { t, type ProtoKey } from './i18n';
import { pp } from './paths';
import { useProtoRole } from './role';
import s from './ScreenIndex.module.css';

interface Screen {
  key: ProtoKey;
  to: string;
}

const screen = (key: string, to: string) => ({ key: `screen.${key}` as ProtoKey, to });

const SEEKER: Screen[] = [
  screen('guestJobs', pp.guest.jobs),
  screen('guestJob', pp.guest.job(101)),
  screen('recommended', pp.seeker.recommended),
  screen('jobs', pp.seeker.jobs),
  screen('job', pp.seeker.job(101)),
  screen('cv', pp.seeker.cv),
  screen('prep', pp.seeker.prep(101)),
  screen('offers', pp.seeker.offers),
  screen('preferences', pp.seeker.preferences),
  screen('account', pp.seeker.account),
];

const SHARED: Screen[] = [screen('login', pp.login), screen('register', pp.register), screen('consent', pp.consent)];

const COMPANY: Screen[] = [
  screen('companyJobs', pp.company.jobs),
  screen('jobNew', pp.company.jobNew),
  screen('jobEdit', pp.company.jobEdit(102)),
  screen('applicants', pp.company.applicants(101)),
  screen('talent', pp.company.talent(101)),
  screen('sentOffers', pp.company.offers),
  screen('profile', pp.company.profile),
];

function ScreenList({ items }: { items: Screen[] }) {
  return (
    <ul className={s.list}>
      {items.map((x) => (
        <li key={x.to}>
          <Link to={x.to} className={s.item}>
            <span className={s.itemMark} />
            <span className={s.itemText}>
              <span className={s.itemName}>{t(x.key)}</span>
              <span className={s.itemDesc}>{t(`${x.key}.desc` as ProtoKey)}</span>
            </span>
            <span className={s.itemPath}>{x.to.replace(pp.index, '') || '/'}</span>
            <ArrowRightIcon className={s.itemArrow} width={16} height={16} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function ScreenIndex() {
  const { role } = useProtoRole();
  return (
    <main className={s.page}>
      <header className={s.head}>
        <h1 className={s.title}>{t('index.title')}</h1>
        <p className={s.lead}>{t('index.lead')}</p>
      </header>

      <div className={s.fields}>
        <section className={s.field} data-side="seeker" data-dim={role !== 'seeker' || undefined} aria-labelledby="idx-seeker">
          <div className={s.fieldHead}>
            <h2 id="idx-seeker" className={s.fieldTitle}>
              {t('index.seeker')}
              <span className={s.fieldCount}>{t('index.count', { n: SEEKER.length })}</span>
            </h2>
            <p className={s.fieldNote}>{t('index.seekerNote')}</p>
          </div>
          <ScreenList items={SEEKER} />
        </section>

        <section className={s.spine} aria-labelledby="idx-shared">
          <div className={s.fieldHead}>
            <h2 id="idx-shared" className={s.fieldTitle}>
              {t('index.shared')}
              <span className={s.fieldCount}>{t('index.count', { n: SHARED.length })}</span>
            </h2>
            <p className={s.fieldNote}>{t('index.sharedNote')}</p>
          </div>
          <ScreenList items={SHARED} />
        </section>

        <section className={s.field} data-side="company" data-dim={role !== 'company' || undefined} aria-labelledby="idx-company">
          <div className={s.fieldHead}>
            <h2 id="idx-company" className={s.fieldTitle}>
              {t('index.company')}
              <span className={s.fieldCount}>{t('index.count', { n: COMPANY.length })}</span>
            </h2>
            <p className={s.fieldNote}>{t('index.companyNote')}</p>
          </div>
          <ScreenList items={COMPANY} />
        </section>
      </div>

      <div className={s.notes}>
        <section className={s.note}>
          <h2 className={s.noteTitle}>{t('index.rulesTitle')}</h2>
          <ul className={s.ruleList}>
            <li>{t('index.rule1')}</li>
            <li>{t('index.rule2')}</li>
            <li>{t('index.rule3')}</li>
            <li>{t('index.rule4')}</li>
          </ul>
        </section>
        <section className={s.note}>
          <h2 className={s.noteTitle}>{t('index.laterTitle')}</h2>
          <p className={s.noteBody}>{t('index.later')}</p>
        </section>
      </div>
    </main>
  );
}
