import React from 'react';

interface SpinnerProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  variant?: 'primary' | 'secondary' | 'muted';
}

export const Spinner: React.FC<SpinnerProps> = ({
  className = '',
  size = 'md',
  variant = 'primary',
}) => {
  const sizeStyles = {
    sm: 'w-4 h-4 border-2',
    md: 'w-6 h-6 border-2',
    lg: 'w-8 h-8 border-3',
    xl: 'w-12 h-12 border-4',
  };

  const variantStyles = {
    primary: 'border-t-slate-900 border-r-slate-900 border-b-slate-300 border-l-slate-300 dark:border-t-slate-100 dark:border-r-slate-100 dark:border-b-slate-400 dark:border-l-slate-400',
    secondary: 'border-t-blue-600 border-r-blue-600 border-b-blue-300 border-l-blue-300 dark:border-t-blue-400 dark:border-r-blue-400 dark:border-b-blue-500 dark:border-l-blue-500',
    muted: 'border-t-slate-400 border-r-slate-400 border-b-slate-200 border-l-slate-200 dark:border-t-slate-600 dark:border-r-slate-600 dark:border-b-slate-500 dark:border-l-slate-500',
  };

  return (
    <div
      className={`inline-block rounded-full animate-spin ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      aria-label="Loading"
      role="status"
    />
  );
};

export const SpinnerOverlay: React.FC<{ open: boolean; className?: string }> = ({
  open,
  className = '',
}) => {
  if (!open) return null;

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-black/30 dark:bg-black/60 backdrop-blur-sm ${className}`}
      aria-hidden="true"
    >
      <Spinner size="xl" variant="primary" className="shadow-lg" />
    </div>
  );
};

export const SpinnerInline: React.FC<{ className?: string }> = ({ className = '' }) => (
  <span className={`inline-block align-middle ${className}`}>
    <Spinner size="sm" variant="muted" />
  </span>
);

export const LoadingButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }> = ({
  children,
  loading = false,
  disabled = false,
  className = '',
  ...props
}) => (
  <button
    className={`relative inline-flex items-center justify-center gap-2 ${className} ${loading ? 'cursor-not-allowed opacity-75' : ''} `}
    disabled={disabled || loading}
    {...props}
  >
    {loading && <Spinner size="sm" variant="primary" className="absolute left-2" />}
    <span className={loading ? 'pl-6' : ''}>{children}</span>
  </button>
);