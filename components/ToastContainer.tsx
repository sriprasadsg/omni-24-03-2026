import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircleIcon, XCircleIcon, InfoIcon, XIcon } from './icons';
import { ToastEvent, EVENT_NAME } from '../utils/toast';

const ICONS = {
  success: <CheckCircleIcon size={16} className="text-green-400 flex-shrink-0" />,
  error: <XCircleIcon size={16} className="text-red-400 flex-shrink-0" />,
  info: <InfoIcon size={16} className="text-blue-400 flex-shrink-0" />,
};

const BG = {
  success: 'border-green-500/30 bg-green-500/10',
  error: 'border-red-500/30 bg-red-500/10',
  info: 'border-blue-500/30 bg-blue-500/10',
};

interface ActiveToast extends ToastEvent {
  exiting: boolean;
}

const ToastItem: React.FC<{ toast: ActiveToast; onDismiss: (id: string) => void }> = ({ toast, onDismiss }) => {
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    const start = Date.now();
    const tick = setInterval(() => {
      const elapsed = Date.now() - start;
      const pct = Math.max(0, 100 - (elapsed / toast.duration) * 100);
      setProgress(pct);
      if (elapsed >= toast.duration) {
        clearInterval(tick);
        onDismiss(toast.id);
      }
    }, 80);
    return () => clearInterval(tick);
  }, [toast.id, toast.duration, onDismiss]);

  const barColor = toast.type === 'success' ? 'bg-green-500' : toast.type === 'error' ? 'bg-red-500' : 'bg-blue-500';

  return (
    <div
      className={`w-80 border rounded-xl shadow-2xl overflow-hidden bg-[#1e1e2e] ${BG[toast.type]}
                  animate-in slide-in-from-right-4 fade-in duration-300`}
      role="alert"
    >
      <div className={`h-0.5 ${barColor} transition-all duration-75 ease-linear`} style={{ width: `${progress}%` }} />
      <div className="p-3.5 flex items-start gap-3">
        {ICONS[toast.type]}
        <p className="flex-1 text-sm text-gray-200 leading-relaxed">{toast.message}</p>
        <button
          onClick={() => onDismiss(toast.id)}
          className="flex-shrink-0 p-0.5 text-gray-500 hover:text-gray-300 rounded transition-colors"
          title="Dismiss"
        >
          <XIcon size={13} />
        </button>
      </div>
    </div>
  );
};

const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<ActiveToast[]>([]);

  useEffect(() => {
    const handler = (e: Event) => {
      const { detail } = e as CustomEvent<ToastEvent>;
      setToasts(prev => [...prev, { ...detail, exiting: false }]);
    };
    window.addEventListener(EVENT_NAME, handler);
    return () => window.removeEventListener(EVENT_NAME, handler);
  }, []);

  const dismiss = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  if (toasts.length === 0) return null;

  return createPortal(
    <div
      className="fixed bottom-6 right-6 z-[9998] flex flex-col gap-3 items-end pointer-events-none"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map(t => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem toast={t} onDismiss={dismiss} />
        </div>
      ))}
    </div>,
    document.body
  );
};

export default ToastContainer;
