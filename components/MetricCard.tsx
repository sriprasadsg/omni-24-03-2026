import React from 'react';
import { Metric, MetricType } from '../types';
import { ArrowUpRightIcon, ArrowDownRightIcon, CpuIcon, MemoryStickIcon, HardDriveIcon, WifiIcon, AlertTriangleIcon } from './icons';

interface MetricCardProps {
  metric: Metric;
  index?: number;
}

const METRIC_CONFIG: Record<MetricType, { icon: React.ReactNode; gradient: string; glow: string }> = {
  cpu:            { icon: <CpuIcon className="w-5 h-5" />,           gradient: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', glow: 'rgba(59,130,246,0.3)' },
  memory:         { icon: <MemoryStickIcon className="w-5 h-5" />,   gradient: 'linear-gradient(135deg, #10b981, #059669)', glow: 'rgba(16,185,129,0.3)' },
  disk:           { icon: <HardDriveIcon className="w-5 h-5" />,     gradient: 'linear-gradient(135deg, #f59e0b, #d97706)', glow: 'rgba(245,158,11,0.3)' },
  network:        { icon: <WifiIcon className="w-5 h-5" />,          gradient: 'linear-gradient(135deg, #a855f7, #7c3aed)', glow: 'rgba(168,85,247,0.3)' },
  security_event: { icon: <AlertTriangleIcon className="w-5 h-5" />, gradient: 'linear-gradient(135deg, #ef4444, #dc2626)', glow: 'rgba(239,68,68,0.3)' },
};

const FALLBACK_CONFIG = { icon: <CpuIcon className="w-5 h-5" />, gradient: 'linear-gradient(135deg, #64748b, #475569)', glow: 'rgba(100,116,139,0.3)' };

export const MetricCard: React.FC<MetricCardProps> = ({ metric, index = 0 }) => {
  const cfg = METRIC_CONFIG[metric.type] ?? FALLBACK_CONFIG;
  const isUp = metric.changeType === 'increase';

  return (
    <div
      className="glass rounded-2xl p-5 flex items-center justify-between group cursor-pointer slide-up"
      style={{
        animationDelay: `${index * 60}ms`,
        transition: 'box-shadow 0.25s ease, transform 0.2s ease, border-color 0.25s ease',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)';
        (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${cfg.glow}, 0 0 0 1px rgba(255,255,255,0.08)`;
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.transform = '';
        (e.currentTarget as HTMLDivElement).style.boxShadow = '';
      }}
    >
      <div className="flex items-center gap-4">
        {/* Gradient icon container */}
        <div
          className="flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center text-white transition-transform duration-300 group-hover:scale-110"
          style={{ background: cfg.gradient, boxShadow: `0 4px 12px ${cfg.glow}` }}
        >
          {cfg.icon}
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-0.5">
            {metric.title}
          </p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight leading-none">
            {metric.value}
          </p>
        </div>
      </div>

      {/* Trend badge */}
      <div
        className="flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold"
        style={{
          background: isUp ? 'rgba(239,68,68,0.12)' : 'rgba(16,185,129,0.12)',
          border: `1px solid ${isUp ? 'rgba(239,68,68,0.25)' : 'rgba(16,185,129,0.25)'}`,
          color: isUp ? '#f87171' : '#34d399',
        }}
      >
        {isUp ? <ArrowUpRightIcon size={13} /> : <ArrowDownRightIcon size={13} />}
        {metric.change}
      </div>
    </div>
  );
};
