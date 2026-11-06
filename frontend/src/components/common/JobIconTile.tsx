import { jobIcon, jobIconGroup } from './jobIcon';
import { cx } from './Page';
import ui from './ui.module.css';

const ICON_PX = { sm: 20, md: 24, lg: 28 } as const;

/**
 * The job-type icon on its tile (DESIGN.md Job icon): the same rounded mint square for every group, so cards stay
 * uniform. Decorative: the job title next to it is the text. `sm` (40 px) leads job rows in lists.
 */
export function JobIconTile({
  title,
  category,
  size = 'md',
  className,
}: {
  title: string;
  category?: string | null;
  size?: keyof typeof ICON_PX;
  className?: string;
}) {
  const Icon = jobIcon(title, category);
  const px = ICON_PX[size];
  return (
    <span className={cx(ui.jobTile, className)} data-size={size} data-group={jobIconGroup(title, category)} aria-hidden="true">
      <Icon width={px} height={px} />
    </span>
  );
}
