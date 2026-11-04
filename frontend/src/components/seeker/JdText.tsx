import type { ReactNode } from 'react';
import s from './seeker.module.css';

// JD section headings as the JD draft (D24) and most postings write them
const HEADINGS = ['주요 업무', '자격 요건', '우대 사항'];

/** Renders JD text: known section headings as headings, "- " lines as lists, other lines as paragraphs. */
export default function JdText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`l${blocks.length}`}>
          {list.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>,
      );
    }
    list = [];
  };
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
      list.push(trimmed.slice(2));
      continue;
    }
    flush();
    if (!trimmed) continue;
    if (HEADINGS.includes(trimmed)) blocks.push(<h3 key={`h${blocks.length}`}>{trimmed}</h3>);
    else blocks.push(<p key={`p${blocks.length}`}>{line}</p>);
  }
  flush();
  return <div className={s.jd}>{blocks}</div>;
}
