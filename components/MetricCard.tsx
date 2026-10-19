import React, { useId } from 'react';
import { Metric, MetricType } from '../types';
import { ArrowUpRightIcon, ArrowDownRightIcon, CpuIcon, MemoryStickIcon, HardDriveIcon, WifiIcon, AlertTriangleIcon } from './icons';

interface MetricCardProps {
  metric: Metric;
  index?: number;
}

// Spatial Glass KPI tile: tinted icon chip, large tabular value, trend pill and a sparkline drawn
// from the metric's own data points (inline SVG, no chart library per tile).
const METRIC_CONFIG: Record<MetricType, { icon: React.ReactNode; color: string; chip: string }> = {
  cpu:            { icon: <CpuIcon className="w-[18px] h-[18px]" />,           color: '#3b82f6', chip: 'text-blue-600 dark:text-blue-400 bg-blue-500/10 ring-blue-500/20' },
  memory:         { icon: <MemoryStickIcon className="w-[18px] h-[18px]" />,   color: '#10b981', chip: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 ring-emerald-500/20' },
  disk:           { icon: <HardDriveIcon className="w-[18px] h-[18px]" />,     color: '#f59e0b', chip: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 ring-amber-500/20' },
  network:        { icon: <WifiIcon className="w-[18px] h-[18px]" />,          color: '#22d3ee', chip: 'text-primary-600 dark:text-primary-400 bg-primary-500/10 ring-primary-500/20' },
  security_event: { icon: <AlertTriangleIcon className="w-[18px] h-[18px]" />, color: '#ef4444', chip: 'text-red-600 dark:text-red-400 bg-red-500/10 ring-red-500/20' },
};

const FALLBACK_CONFIG = { icon: <CpuIcon className="w-[18px] h-[18px]" />, color: '#637089', chip: 'text-gray-600 dark:text-gray-300 bg-gray-500/10 ring-gray-500/20' };

const Sparkline: React.FC<{ values: number[]; color: string }> = ({ values, color }) => {
  const gradientId = useId();
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => [(i / (values.length - 1)) * 100, 30 - ((v - min) / span) * 26]);
  const line = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  return (
    <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="w-full h-10" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L100,32 L0,32 Z`} fill={`url(#${gradientId})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
};

export const MetricCard: React.FC<MetricCardProps> = ({ metric, index = 0 }) => {
  const cfg = METRIC_CONFIG[metric.type] ?? FALLBACK_CONFIG;
  const isUp = metric.changeType === 'increase';
  const values = (metric.data ?? []).map(d => d.value).filter(v => Number.isFinite(v));

  return (
    <div
      className="group relative overflow-hidden rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card hover:shadow-card-hover hover:-translate-y-0.5 transition-all duration-200 slide-up"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="p-5 pb-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <span className={`grid place-items-center h-9 w-9 flex-shrink-0 rounded-xl ring-1 ring-inset ${cfg.chip}`}>{cfg.icon}</span>
            <p className="text-[13px] font-medium text-gray-600 dark:text-gray-400 truncate">{metric.title}</p>
          </div>
          <span
            className={`flex-shrink-0 inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[11px] font-semibold ring-1 ring-inset ${isUp
              ? 'text-red-600 dark:text-red-400 bg-red-500/10 ring-red-500/20'
              : 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 ring-emerald-500/20'}`}
          >
            {isUp ? <ArrowUpRightIcon size={12} /> : <ArrowDownRightIcon size={12} />}
            {metric.change}
          </span>
        </div>
        <p className="mt-3 text-[32px] leading-none font-semibold tracking-[-0.03em] tabular-nums text-gray-900 dark:text-white">
          {metric.value}
        </p>
      </div>
      <div className="mt-2 opacity-90 group-hover:opacity-100 transition-opacity">
        <Sparkline values={values} color={cfg.color} />
      </div>
    </div>
  );
};
