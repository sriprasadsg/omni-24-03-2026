/**
 * Global toast utility — uses a CustomEvent bus so no context or prop-drilling
 * is needed. Any component can call showToast() and ToastContainer will render it.
 */

export type ToastType = 'success' | 'error' | 'info';

export interface ToastEvent {
  id: string;
  message: string;
  type: ToastType;
  duration: number; // ms
}

const EVENT_NAME = 'app:toast';

let _counter = 0;

export function showToast(
  message: string,
  type: ToastType = 'info',
  duration?: number
): void {
  const defaultDuration = type === 'error' ? 6000 : 4000;
  const detail: ToastEvent = {
    id: `toast-${++_counter}-${Date.now()}`,
    message,
    type,
    duration: duration ?? defaultDuration,
  };
  window.dispatchEvent(new CustomEvent<ToastEvent>(EVENT_NAME, { detail }));
}

export { EVENT_NAME };
