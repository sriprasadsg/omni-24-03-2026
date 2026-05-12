import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  Cpu, 
  Database, 
  Activity, 
  Zap, 
  Lock, 
  RefreshCcw, 
  Workflow,
  Globe
} from 'lucide-react';

const FutureTechDashboard: React.FC = () => {
  const [swarmNodes, setSwarmNodes] = useState(10245);
  const [enclaveHealth, setEnclaveHealth] = useState(99.98);
  const [pqcStandard, setPqcStandard] = useState('Kyber-768 Hybrid');

  return (
    <div className="p-8 bg-[#040812] min-h-screen text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex justify-between items-end mb-10">
          <div>
            <h1 className="text-4xl font-black tracking-tight mb-2 bg-gradient-to-r from-cyan-400 to-indigo-500 bg-clip-text text-transparent">
              2027 INNOVATION HORIZON
            </h1>
            <p className="text-slate-400 text-lg">Autonomous Intelligence & Quantum Resilience Engine</p>
          </div>
          <div className="flex gap-3">
            <span className="px-3 py-1 bg-cyan-500/10 border border-cyan-500/30 rounded-full text-cyan-400 text-xs font-bold tracking-widest uppercase">
              Live Preview
            </span>
            <span className="px-3 py-1 bg-indigo-500/10 border border-indigo-500/30 rounded-full text-indigo-400 text-xs font-bold tracking-widest uppercase">
              Quantum Secure
            </span>
          </div>
        </div>

        {/* Top Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          {[
            { label: 'Active Enclaves', value: '42', icon: Cpu, color: 'text-cyan-400' },
            { label: 'Swarm Nodes', value: swarmNodes.toLocaleString(), icon: Globe, color: 'text-indigo-400' },
            { label: 'Integrity Proofs', value: '1.2M', icon: Database, color: 'text-emerald-400' },
            { label: 'PQC Handshakes', value: '8.4k/s', icon: Zap, color: 'text-amber-400' },
          ].map((stat, i) => (
            <div key={i} className="bg-slate-900/50 border border-slate-800 p-6 rounded-2xl backdrop-blur-sm">
              <div className="flex justify-between items-start mb-4">
                <div className={`p-2 rounded-lg bg-slate-800 ${stat.color}`}>
                  <stat.icon size={20} />
                </div>
                <Activity size={16} className="text-slate-700" />
              </div>
              <p className="text-slate-500 text-sm font-medium mb-1">{stat.label}</p>
              <h3 className="text-3xl font-bold">{stat.value}</h3>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* 1. Digital Provenance & Integrity */}
          <div className="lg:col-span-2 space-y-8">
            <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-8">
              <div className="flex items-center gap-4 mb-8">
                <div className="p-3 bg-emerald-500/10 rounded-2xl text-emerald-400">
                  <Database size={24} />
                </div>
                <div>
                  <h2 className="text-xl font-bold">Digital Provenance Ledger</h2>
                  <p className="text-sm text-slate-500">Merkle-Chained Immutable Log Verification</p>
                </div>
              </div>
              
              <div className="space-y-4">
                {[1, 2, 3].map((_, i) => (
                  <div key={i} className="flex items-center gap-6 p-4 bg-slate-950/50 rounded-xl border border-slate-800">
                    <div className="flex-shrink-0 w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <div className="flex-grow">
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-xs font-mono text-slate-500 uppercase tracking-wider">Block #{42000 + i}</span>
                        <span className="text-[10px] text-slate-600 font-mono">0x74f...8a2e</span>
                      </div>
                      <p className="text-sm font-medium">Log Batch Verified • {12 + i} Entries</p>
                    </div>
                    <div className="flex items-center gap-2 text-emerald-400">
                      <ShieldCheck size={16} />
                      <span className="text-xs font-bold">SIGNED</span>
                    </div>
                  </div>
                ))}
              </div>
              <button className="w-full mt-6 py-3 text-sm font-bold text-slate-400 border border-dashed border-slate-700 rounded-xl hover:bg-slate-800/50 transition-all">
                Audit Full Chain History
              </button>
            </div>

            {/* 2. Swarm Immunity */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-8 relative overflow-hidden">
               <div className="absolute top-0 right-0 p-8 opacity-10">
                  <Workflow size={120} />
               </div>
               <div className="relative">
                <div className="flex items-center gap-4 mb-8">
                  <div className="p-3 bg-indigo-500/10 rounded-2xl text-indigo-400">
                    <Workflow size={24} />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold">Digital Immune Swarm</h2>
                    <p className="text-sm text-slate-500">Autonomous Antibody Propagation (10,000 Nodes)</p>
                  </div>
                </div>

                <div className="flex items-center justify-between p-6 bg-indigo-500/5 border border-indigo-500/20 rounded-2xl">
                  <div className="flex items-center gap-4">
                    <RefreshCcw className="text-indigo-400 animate-spin-slow" size={32} />
                    <div>
                      <p className="text-sm font-bold text-indigo-300">Active Learning Loop</p>
                      <p className="text-xs text-indigo-400/70 italic">Synthesizing defense rules from recent edge anomalies...</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-black">99.99%</p>
                    <p className="text-[10px] text-indigo-400 font-bold tracking-tighter uppercase">Immunity Coverage</p>
                  </div>
                </div>
               </div>
            </div>
          </div>

          {/* Sidebar Area: PQC & Enclaves */}
          <div className="space-y-8">
            {/* Crypto-Agility Card */}
            <div className="bg-gradient-to-br from-indigo-900/40 to-slate-900/40 border border-indigo-500/20 rounded-3xl p-8">
              <div className="p-3 bg-indigo-500/10 rounded-2xl text-indigo-400 w-fit mb-6">
                <Lock size={24} />
              </div>
              <h3 className="text-xl font-bold mb-2">Crypto-Agility Hub</h3>
              <p className="text-sm text-indigo-300/60 mb-6">Real-time PQC Migration & Management</p>
              
              <div className="space-y-4">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-500">Active Standard</span>
                  <span className="font-bold text-indigo-400">{pqcStandard}</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-500">Classical Fallback</span>
                  <span className="font-bold">X25519 (ECC)</span>
                </div>
                <div className="pt-4 border-t border-indigo-500/10">
                   <div className="w-full h-1 bg-slate-800 rounded-full mb-2">
                      <div className="w-4/5 h-full bg-indigo-500 rounded-full shadow-[0_0_10px_rgba(99,102,241,0.5)]" />
                   </div>
                   <p className="text-[10px] text-center text-indigo-400 font-bold uppercase tracking-tighter">
                      Fleet Migration Progress: 80%
                   </p>
                </div>
              </div>
            </div>

            {/* Confidential Computing Card */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-8">
              <div className="p-3 bg-cyan-500/10 rounded-2xl text-cyan-400 w-fit mb-6">
                <Cpu size={24} />
              </div>
              <h3 className="text-xl font-bold mb-2">Enclave Health</h3>
              <p className="text-sm text-slate-500 mb-6">TEE Attestation & Isolation Status</p>

              <div className="flex items-center gap-4 p-4 bg-cyan-500/5 border border-cyan-500/20 rounded-xl mb-4">
                <ShieldCheck className="text-cyan-400" size={20} />
                <span className="text-xs font-bold text-cyan-300">HW-Attestation Verified</span>
              </div>

              <div className="space-y-3">
                 {[
                   { label: 'Isolated Memory', val: '64GB' },
                   { label: 'Attestation Std', val: 'DCAP v3' },
                   { label: 'Hardware Key', val: 'TPM 2.0+' }
                 ].map((row, i) => (
                   <div key={i} className="flex justify-between items-center text-xs">
                      <span className="text-slate-500">{row.label}</span>
                      <span className="font-mono text-cyan-400">{row.val}</span>
                   </div>
                 ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FutureTechDashboard;
