import { jobIcon, jobIconGroup } from './jobIcon';
import ui from './ui.module.css';

/**
 * The job-type icon on its tile (DESIGN.md Job icon): the same rounded mint square for every group, so cards stay
 * uniform. Decorative: the job title next to it is the text.
 */
export function JobIconTile({ title, category, size = 'md' }: { title: string; category?: string | null; size?: 'md' | 'lg' }) {
  const Icon = jobIcon(title, category);
  const px = size === 'lg' ? 28 : 24;
  return (
    <span className={ui.jobTile} data-size={size} data-group={jobIconGroup(title, category)} aria-hidden="true">
      <Icon width={px} height={px} />
    </span>
  );
}
