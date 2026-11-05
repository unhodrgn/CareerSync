import type { ComponentType, SVGProps } from 'react';
import {
  BriefcaseIcon,
  ChartIcon,
  CheckCircleIcon,
  ChipIcon,
  ClipboardIcon,
  CloudIcon,
  MonitorCodeIcon,
  PaletteIcon,
  PhoneIcon,
  ServerIcon,
  ShieldIcon,
} from '@/components/common/icons';

// An illustrative icon for a job, picked from its type (DESIGN.md Job icon). Purely decorative: it is not a
// company logo and carries no meaning beyond "this looks like a backend job". Jobs have no category field yet,
// so the title decides; pass `category` first once one exists.

export type JobIconGroup =
  | 'security'
  | 'ai'
  | 'data'
  | 'infra'
  | 'mobile'
  | 'qa'
  | 'frontend'
  | 'backend'
  | 'design'
  | 'pm'
  | 'default';

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

/**
 * Checked top to bottom; the first group with a matching keyword wins, so the order settles overlaps:
 * "React Native" is mobile before frontend, "QA (Java)" is QA before backend. Korean keywords match anywhere in the
 * title; Latin ones only as whole words, so "ai" does not match "maintain" and "pm" does not match "npm".
 * To add a group or keyword, edit this list.
 */
export const JOB_ICON_GROUPS: { group: Exclude<JobIconGroup, 'default'>; icon: Icon; keywords: string[] }[] = [
  { group: 'security', icon: ShieldIcon, keywords: ['보안', '정보보호', '시큐리티', 'security'] },
  { group: 'ai', icon: ChipIcon, keywords: ['인공지능', '머신러닝', '딥러닝', 'ai', 'ml', 'llm', 'mlops'] },
  { group: 'data', icon: ChartIcon, keywords: ['데이터', '분석', 'data', 'analyst', 'analytics', 'bi'] },
  {
    group: 'infra',
    icon: CloudIcon,
    keywords: ['인프라', '데브옵스', '클라우드', '쿠버네티스', 'infra', 'devops', 'cloud', 'sre', 'kubernetes'],
  },
  {
    group: 'mobile',
    icon: PhoneIcon,
    keywords: ['모바일', '안드로이드', '앱 개발', 'mobile', 'ios', 'android', 'flutter', 'react native'],
  },
  { group: 'qa', icon: CheckCircleIcon, keywords: ['테스트', '품질', 'qa', 'test', 'sdet'] },
  {
    group: 'frontend',
    icon: MonitorCodeIcon,
    keywords: ['프론트엔드', '프런트엔드', '퍼블리셔', 'frontend', 'front-end', 'react', 'vue'],
  },
  {
    group: 'backend',
    icon: ServerIcon,
    keywords: ['백엔드', '서버', 'backend', 'server', 'java', 'spring', 'node', 'django', 'api'],
  },
  { group: 'design', icon: PaletteIcon, keywords: ['디자이너', '디자인', 'design', 'ux', 'ui'] },
  { group: 'pm', icon: ClipboardIcon, keywords: ['기획', '프로덕트 매니저', '사업', 'pm', 'po', 'product manager'] },
];

const LATIN = /^[a-z0-9 .+#-]+$/;

function matches(text: string, keyword: string): boolean {
  if (!LATIN.test(keyword)) return text.includes(keyword);
  // A whole word: no Latin letter or digit right before or after it (Korean or punctuation is fine)
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(^|[^a-z0-9])${escaped}($|[^a-z0-9])`).test(text);
}

/** The icon group for a job: its category when it has one, else its title; `default` when nothing matches. */
export function jobIconGroup(title: string, category?: string | null): JobIconGroup {
  for (const source of [category, title]) {
    const text = (source ?? '').toLowerCase();
    if (!text) continue;
    const found = JOB_ICON_GROUPS.find((g) => g.keywords.some((k) => matches(text, k)));
    if (found) return found.group;
  }
  return 'default';
}

/** The icon component for a job (briefcase by default). */
export function jobIcon(title: string, category?: string | null): Icon {
  const group = jobIconGroup(title, category);
  return JOB_ICON_GROUPS.find((g) => g.group === group)?.icon ?? BriefcaseIcon;
}
