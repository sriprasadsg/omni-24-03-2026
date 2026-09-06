import React from 'react';

interface ContextCardProps {
  type: 'finding' | 'recommendation' | 'metric' | 'alert';
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  metadata?: Record<string, any>;
}

const typeStyles = {
  finding: {
    icon: '🔍',
    borderColor: 'border-amber-500',
    bgColor: 'bg-amber-500/10',
    textColor: 'text-amber-300',
  },
  recommendation: {
    icon: '💡',
    borderColor: 'border-emerald-500',
    bgColor: 'bg-emerald-500/10',
    textColor: 'text-emerald-300',
  },
  metric: {
    icon: '📊',
    borderColor: 'border-blue-500',
    bgColor: 'bg-blue-500/10',
    textColor: 'text-blue-300',
  },
  alert: {
    icon: '⚠️',
    borderColor: 'border-red-500',
    bgColor: 'bg-red-500/10',
    textColor: 'text-red-300',
  },
};

export const ContextCard: React.FC<ContextCardProps> = ({
  type,
  title,
  description,
  actionLabel,
  onAction,
  metadata,
}) => {
  const styles = typeStyles[type];

  return (
    <div className={`p-4 rounded-lg border-l-4 ${styles.borderColor} ${styles.bgColor} my-2`}>
      <div className="flex items-start gap-3">
        <span className="text-xl">{styles.icon}</span>
        <div className="flex-1">
          <div className={`font-semibold ${styles.textColor}`}>{title}</div>
          <div className="text-slate-300 mt-1">{description}</div>
          {metadata && (
            <div className="mt-2 text-xs text-slate-500">
              {Object.entries(metadata).map(([k, v]) => (
                <div key={k}><span className="font-mono">{k}:</span> {String(v)}</div>
              ))}
            </div>
          )}
          {actionLabel && onAction && (
            <button
              onClick={onAction}
              className={`mt-3 text-sm font-medium ${styles.textColor} hover:underline`}
            >
              {actionLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};