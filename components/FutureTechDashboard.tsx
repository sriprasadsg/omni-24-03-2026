import React, { useEffect, useState } from 'react';
import { ShieldCheck, Cpu, Database, Lock, Globe, AlertTriangle } from 'lucide-react';
import { authFetch, fetchCryptoInventory, fetchAgents } from '../services/apiService';
import { CryptographicInventory } from '../types';

interface ProvenanceStatus { chain_length: number; latest_hash: string | null; standard?: string }

// Built from live sources (provenance chain, crypto inventory, agent fleet);
// this page used to be a static mock-up with invented figures.
export const horizonSummary = (inventory: CryptographicInventory[], agents: any[]) => ({
    cryptoAssets: inventory.length,
    quantumVulnerable: inventory.filter(i => i.quantumVulnerable).length,
    agentsOnline: agents.filter(a => String(a.status || '').toLowerCase() === 'online').length,
    agentsTotal: agents.length,
});

const FutureTechDashboard: React.FC = () => {
  const [provenance, setProvenance] = useState<ProvenanceStatus | null>(null);
  const [inventory, setInventory] = useState<CryptographicInventory[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      const [prov, inv, ag] = await Promise.all([
        authFetch('/api/provenance/status').then(r => (r.ok ? r.json() : null)).catch(() => null),
        fetchCryptoInventory(),
        fetchAgents(),
      ]);
      setProvenance(prov);
      setInventory(Array.isArray(inv) ? inv : []);
      setAgents(Array.isArray(ag) ? ag : []);
      setLoaded(true);
    })();
  }, []);

  const s = horizonSummary(inventory, agents);
  const dash = (v: string | number) => (loaded ? String(v) : '…');
  const stats = [
    { label: 'Provenance Blocks', value: dash(provenance ? provenance.chain_length : '—'), icon: Database, color: 'text-emerald-600 dark:text-emerald-400' },
    { label: 'Crypto Assets Tracked', value: dash(s.cryptoAssets), icon: Lock, color: 'text-cyan-600 dark:text-cyan-400' },
    { label: 'Quantum-Vulnerable', value: dash(s.quantumVulnerable), icon: AlertTriangle, color: 'text-amber-700 dark:text-amber-400' },
    { label: 'Agents Online', value: dash(`${s.agentsOnline} / ${s.agentsTotal}`), icon: Globe, color: 'text-indigo-600 dark:text-indigo-400' },
  ];
  const vulnerable = inventory.filter(i => i.quantumVulnerable);

  return (
    <div className="p-8 bg-transparent dark:bg-[#040812] min-h-screen text-gray-900 dark:text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto">
        <div className="mb-10">
          <h1 className="text-4xl font-black tracking-tight mb-2 bg-gradient-to-r from-cyan-400 to-indigo-500 bg-clip-text text-transparent">
            2027 HORIZON
          </h1>
          <p className="text-gray-600 dark:text-slate-400 text-lg">Log provenance and post-quantum readiness</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          {stats.map(stat => (
            <div key={stat.label} className="bg-white/50 dark:bg-slate-900/50 border border-gray-200 dark:border-slate-800 p-6 rounded-2xl backdrop-blur-sm">
              <div className={`p-2 rounded-lg bg-white dark:bg-slate-800 w-fit mb-4 ${stat.color}`}>
                <stat.icon size={20} />
              </div>
              <p className="text-slate-500 text-sm font-medium mb-1">{stat.label}</p>
              <h3 className="text-3xl font-bold">{stat.value}</h3>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="bg-white/50 dark:bg-slate-900/50 border border-gray-200 dark:border-slate-800 rounded-3xl p-8">
            <div className="flex items-center gap-4 mb-6">
              <div className="p-3 bg-emerald-500/10 rounded-2xl text-emerald-600 dark:text-emerald-400"><ShieldCheck size={24} /></div>
              <div>
                <h2 className="text-xl font-bold">Provenance Ledger</h2>
                <p className="text-sm text-slate-500">Merkle-chained log blocks signed by this server</p>
              </div>
            </div>
            {!loaded ? null : !provenance ? (
              <p className="text-sm text-slate-500">Provenance status unavailable.</p>
            ) : provenance.chain_length === 0 ? (
              <p className="text-sm text-slate-500">No log blocks have been signed since the backend started.</p>
            ) : (
              <div className="space-y-2 text-sm">
                <p><span className="text-slate-500">Blocks in chain:</span> {provenance.chain_length}</p>
                <p className="font-mono text-xs break-all"><span className="text-slate-500 font-sans">Latest hash:</span> {provenance.latest_hash}</p>
              </div>
            )}
          </div>

          <div className="bg-white/50 dark:bg-slate-900/50 border border-gray-200 dark:border-slate-800 rounded-3xl p-8">
            <div className="flex items-center gap-4 mb-6">
              <div className="p-3 bg-cyan-500/10 rounded-2xl text-cyan-600 dark:text-cyan-400"><Cpu size={24} /></div>
              <div>
                <h2 className="text-xl font-bold">Crypto-Agility</h2>
                <p className="text-sm text-slate-500">Algorithms in use that need a post-quantum replacement</p>
              </div>
            </div>
            {loaded && inventory.length === 0 ? (
              <p className="text-sm text-slate-500">No cryptographic inventory recorded yet.</p>
            ) : loaded && vulnerable.length === 0 ? (
              <p className="text-sm text-emerald-600 dark:text-emerald-400">None of the {inventory.length} tracked algorithms is quantum-vulnerable.</p>
            ) : (
              <ul className="divide-y divide-gray-200 dark:divide-slate-800 text-sm">
                {vulnerable.slice(0, 8).map(item => (
                  <li key={item.id} className="py-2 flex justify-between gap-4">
                    <span><span className="font-semibold">{item.algorithm}</span> <span className="text-slate-500">· {item.usage}</span></span>
                    <span className="text-amber-700 dark:text-amber-400 text-xs whitespace-nowrap">→ {item.replacementAlgorithm || 'replacement TBD'} ({item.migrationPriority})</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FutureTechDashboard;
