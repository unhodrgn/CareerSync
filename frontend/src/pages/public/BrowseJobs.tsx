import { useAuth } from '@/auth/AuthContext';
import { cx, PageHead } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import h from '@/styles/hiring.module.css';
import { t } from '@/i18n';
import Home from './Home';
import { JobDiscovery } from './JobList';

export default function BrowseJobs() {
  const { user } = useAuth();
  if (!user) return <Home />;

  return (
    <div className={cx(ui.page, h.page)}>
      <PageHead title={t('jobs.title')} />
      <JobDiscovery editorial />
    </div>
  );
}
