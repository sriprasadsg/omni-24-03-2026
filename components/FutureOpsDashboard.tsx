import React from 'react';
import { Cpu, Activity, Globe, Zap } from 'lucide-react';

const FutureOpsDashboard: React.FC = () => {
  return (
    <div className="p-8 bg-[#040812] min-h-screen text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-end mb-10">
          <div>
            <h1 className="text-4xl font-black tracking-tight mb-2 bg-gradient-to-r from-cyan-400 to-indigo-500 bg-clip-text text-transparent">
              FUTURE OPERATIONS
            </h1>
            <p className="text-slate-400 text-lg">Autonomous Unified Operations Engine</p>
          </div>
          <span className="px-3 py-1 bg-cyan-500/10 border border-cyan-500/30 rounded-full text-cyan-400 text-xs font-bold tracking-widest uppercase">
            Live Preview
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          {[
            { label: 'Active Operations', value: '128', icon: Activity, color: 'text-emerald-400' },
            { label: 'Autonomous Tasks', value: '2.4k', icon: Zap, color: 'text-amber-400' },
            { label: 'Unified Endpoints', value: '86', icon: Globe, color: 'text-indigo-400' },
            { label: 'Systems Online', value: '100%', icon: Cpu, color: 'text-cyan-400' },
          ].map((stat, i) => (
            <div key={i} className="bg-slate-900/50 border border-slate-800 p-6 rounded-2xl backdrop-blur-sm">
              <div className="flex justify-between items-start mb-4">
                <div className={`p-2 rounded-lg bg-slate-800 ${stat.color}`}>
                  <stat.icon size={20} />
                </div>
              </div>
              <p className="text-slate-500 text-sm font-medium mb-1">{stat.label}</p>
              <h3 className="text-3xl font-bold">{stat.value}</h3>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default FutureOpsDashboard;
