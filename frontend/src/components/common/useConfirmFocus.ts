import { useEffect, useRef } from 'react';

/**
 * Focus for an inline confirm that replaces its trigger: when `open` turns true, focus moves into the confirm
 * (`regionRef`, give it tabIndex={-1}); when it turns false, focus returns to the trigger, or to `fallbackRef`
 * when the trigger is gone (e.g. the action succeeded and the panel now shows its result).
 */
export function useConfirmFocus<Trigger extends HTMLElement, Region extends HTMLElement, Fallback extends HTMLElement = HTMLElement>(
  open: boolean,
) {
  const triggerRef = useRef<Trigger>(null);
  const regionRef = useRef<Region>(null);
  const fallbackRef = useRef<Fallback>(null);
  const wasOpen = useRef(open);

  useEffect(() => {
    if (open && !wasOpen.current) regionRef.current?.focus();
    if (!open && wasOpen.current) (triggerRef.current ?? fallbackRef.current)?.focus();
    wasOpen.current = open;
  }, [open]);

  return { triggerRef, regionRef, fallbackRef };
}
