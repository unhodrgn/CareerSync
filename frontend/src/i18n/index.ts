import ko from './ko';

export type MessageKey = keyof typeof ko;
/** Shape of a locale file: `export default { ... } satisfies Messages`. */
export type Messages = Record<MessageKey, string>;

export const DEFAULT_LOCALE = 'ko';

// Every other file in this folder is a locale named after the file (vi.ts → 'vi'): adding a language is adding a file
const modules = import.meta.glob<Messages>(['./*.ts', '!./index.ts'], { eager: true, import: 'default' });
const locales: Record<string, Partial<Messages>> = Object.fromEntries(
  Object.entries(modules).map(([path, messages]) => [path.slice('./'.length, -'.ts'.length), messages]),
);

const locale: string = DEFAULT_LOCALE;

/** UI text for `key` in the current locale; falls back to Korean. */
export function t(key: MessageKey): string {
  return locales[locale]?.[key] ?? ko[key];
}
