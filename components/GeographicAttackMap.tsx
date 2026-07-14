import React, { useState, useEffect, useCallback } from 'react';

interface CountryThreat {
  country: string;
  country_code: string;
  event_count: number;
  threat_types: string[];
  last_seen: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
}

interface GeoEvent {
  id: string;
  timestamp: string;
  source_ip: string;
  event_type: string;
  description: string;
}

const SEV_COLOR: Record<string, string> = {
  critical: 'text-red-400',
  high: 'text-orange-400',
  medium: 'text-yellow-400',
  low: 'text-blue-400',
};

const SEV_BG: Record<string, string> = {
  critical: 'bg-red-500/20 border-red-500/30',
  high: 'bg-orange-500/20 border-orange-500/30',
  medium: 'bg-yellow-500/20 border-yellow-500/30',
  low: 'bg-blue-500/20 border-blue-500/30',
};

const MOCK_COUNTRIES: CountryThreat[] = [
  { country: 'Russian Federation', country_code: 'RU', event_count: 1842, threat_types: ['Brute Force', 'C2', 'Phishing'], last_seen: '2 min ago', severity: 'critical' },
  { country: 'China', country_code: 'CN', event_count: 1204, threat_types: ['APT', 'Espionage', 'Vulnerability Scan'], last_seen: '5 min ago', severity: 'critical' },
  { country: 'North Korea', country_code: 'KP', event_count: 634, threat_types: ['Ransomware', 'Cryptocurrency Theft'], last_seen: '18 min ago', severity: 'high' },
  { country: 'Iran', country_code: 'IR', event_count: 421, threat_types: ['DDoS', 'Wiper', 'Phishing'], last_seen: '32 min ago', severity: 'high' },
  { country: 'Brazil', country_code: 'BR', event_count: 298, threat_types: ['Banking Trojan', 'Credential Theft'], last_seen: '45 min ago', severity: 'high' },
  { country: 'India', country_code: 'IN', event_count: 187, threat_types: ['Phishing', 'Spam'], last_seen: '1 hr ago', severity: 'medium' },
  { country: 'United States', country_code: 'US', event_count: 156, threat_types: ['Insider Threat', 'Credential Abuse'], last_seen: '1.2 hr ago', severity: 'medium' },
  { country: 'Vietnam', country_code: 'VN', event_count: 134, threat_types: ['Web Scraping', 'Port Scan'], last_seen: '2 hr ago', severity: 'medium' },
  { country: 'Romania', country_code: 'RO', event_count: 98, threat_types: ['Credit Card Fraud', 'Skimming'], last_seen: '3 hr ago', severity: 'medium' },
  { country: 'Nigeria', country_code: 'NG', event_count: 72, threat_types: ['BEC', 'Advance Fee Fraud'], last_seen: '4 hr ago', severity: 'low' },
];

const RANGES = ['24h', '7d', '30d'];

export default function GeographicAttackMap() {
  const [countries, setCountries] = useState<CountryThreat[]>(MOCK_COUNTRIES);
  const [range, setRange] = useState('24h');
  const [selected, setSelected] = useState<CountryThreat | null>(null);
  const [events, setEvents] = useState<GeoEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/advanced-hunting/geo-sources?range=${range}`, {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('token')}` },
      });
      if (r.ok) {
        const data = await r.json();
        if (Array.isArray(data) && data.length > 0) setCountries(data);
      }
    } catch { /* use mock */ }
  }, [range]);

  useEffect(() => { load(); }, [load]);

  const selectCountry = async (c: CountryThreat) => {
    setSelected(c);
    setLoadingEvents(true);
    try {
      const r = await fetch(`/api/advanced-hunting/geo-sources/${c.country_code}/events?range=${range}`, {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('token')}` },
      });
      if (r.ok) setEvents(await r.json());
      else setEvents([]);
    } catch { setEvents([]); }
    setLoadingEvents(false);
  };

  const totalEvents = countries.reduce((s, c) => s + c.event_count, 0);
  const maxCount = Math.max(...countries.map(c => c.event_count), 1);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Geographic Attack Map</h2>
          <p className="text-sm text-slate-400 mt-0.5">{totalEvents.toLocaleString()} events from {countries.length} countries</p>
        </div>
        <div className="flex rounded-lg overflow-hidden border border-slate-700">
          {RANGES.map(r => (
            <button key={r} onClick={() => setRange(r)}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${range === r ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Heatmap bar */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Threat Origin Heatmap</h3>
        <div className="space-y-2">
          {countries.map(c => (
            <button key={c.country_code} onClick={() => selectCountry(c)}
              className={`w-full flex items-center gap-3 p-2 rounded-lg hover:bg-slate-700/50 transition-colors text-left ${selected?.country_code === c.country_code ? 'bg-slate-700' : ''}`}>
              <div className="w-8 text-center text-lg" title={c.country}>{countryFlag(c.country_code)}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-slate-200 truncate">{c.country}</span>
                  <span className={`text-xs font-bold ${SEV_COLOR[c.severity]}`}>{c.event_count.toLocaleString()}</span>
                </div>
                <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all ${c.severity === 'critical' ? 'bg-red-500' : c.severity === 'high' ? 'bg-orange-500' : c.severity === 'medium' ? 'bg-yellow-500' : 'bg-blue-500'}`}
                    style={{ width: `${(c.event_count / maxCount) * 100}%` }} />
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Drill-down panel */}
      {selected && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-2xl">{countryFlag(selected.country_code)}</span>
              <div>
                <h3 className="font-bold text-white">{selected.country}</h3>
                <div className="flex gap-2 mt-0.5">
                  {selected.threat_types.map(t => (
                    <span key={t} className={`text-xs px-1.5 py-0.5 rounded border ${SEV_BG[selected.severity]}`}>{t}</span>
                  ))}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className={`text-lg font-bold ${SEV_COLOR[selected.severity]}`}>{selected.event_count.toLocaleString()}</div>
              <div className="text-xs text-slate-400">Last: {selected.last_seen}</div>
            </div>
          </div>
          {loadingEvents && <p className="text-sm text-slate-400 animate-pulse">Loading events...</p>}
          {!loadingEvents && events.length === 0 && (
            <p className="text-sm text-slate-400">No detailed events available for this country in this time range.</p>
          )}
          {events.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-slate-400 text-xs">
                  <th className="text-left pb-2 pr-3">Time</th>
                  <th className="text-left pb-2 pr-3">Source IP</th>
                  <th className="text-left pb-2 pr-3">Type</th>
                  <th className="text-left pb-2">Description</th>
                </tr></thead>
                <tbody>{events.slice(0, 10).map(ev => (
                  <tr key={ev.id} className="border-t border-slate-700 text-slate-300">
                    <td className="py-2 pr-3 text-slate-400 whitespace-nowrap">{new Date(ev.timestamp).toLocaleTimeString()}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{ev.source_ip}</td>
                    <td className="py-2 pr-3">{ev.event_type}</td>
                    <td className="py-2 truncate max-w-xs">{ev.description}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function countryFlag(code: string): string {
  const flags: Record<string, string> = {
    RU: '🇷🇺', CN: '🇨🇳', KP: '🇰🇵', IR: '🇮🇷', BR: '🇧🇷',
    IN: '🇮🇳', US: '🇺🇸', VN: '🇻🇳', RO: '🇷🇴', NG: '🇳🇬',
  };
  return flags[code] || '🌍';
}
