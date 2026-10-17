import messages from './messages';

// Prototype-only UI text. It lives here, not in src/i18n/ko.ts, so deleting src/prototype/ removes every
// string with it (a new file inside src/i18n/ would be loaded as a locale).
export type ProtoKey = keyof typeof messages;

/** UI text for `key`; `{name}` placeholders are filled from `vars`. */
export function t(key: ProtoKey, vars?: Record<string, string | number>): string {
  let text: string = messages[key];
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
  return text;
}
