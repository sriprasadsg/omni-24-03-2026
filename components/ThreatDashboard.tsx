import React, { useState, useEffect } from "react";
import { 
  Shield, 
  AlertTriangle, 
  Info, 
  Search, 
  Filter, 
  RefreshCw, 
  Database, 
  Activity,
  User,
  ExternalLink,
  Clock
} from "lucide-react";

interface SIEMEvent {
  id: string;
  time: string;
  severity: "Critical" | "High" | "Medium" | "Low";
  category_name: string;
  class_name: string;
  message: string;
  metadata: {
    product: string;
  };
  actor?: {
    user?: { name: string };
  };
  ingestedAt: string;
}

interface SIEMSummary {
  total_events: number;
  severity_counts: Record<string, number>;
  source_counts: Record<string, number>;
}

const ThreatDashboard: React.FC = () => {
  const [events, setEvents] = useState<SIEMEvent[]>([]);
  const [summary, setSummary] = useState<SIEMSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterSeverity, setFilterSeverity] = useState<string>("All");

  const fetchSIEMData = async () => {
    setLoading(true);
    try {
      const [eventsRes, summaryRes] = await Promise.all([
        fetch("/api/siem/events?limit=50"),
        fetch("/api/siem/summary")
      ]);
      const eventsData = await eventsRes.json();
      const summaryData = await summaryRes.json();
      setEvents(eventsData.events || []);
      setSummary(summaryData);
    } catch (error) {
      console.error("Failed to fetch SIEM data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSIEMData();
    const interval = setInterval(fetchSIEMData, 30000);
    return () => clearInterval(interval);
  }, []);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "Critical": return "text-red-500 bg-red-500/10 border-red-500/20";
      case "High": return "text-orange-500 bg-orange-500/10 border-orange-500/20";
      case "Medium": return "text-yellow-500 bg-yellow-500/10 border-yellow-500/20";
      default: return "text-blue-500 bg-blue-500/10 border-blue-500/20";
    }
  };

  const filteredEvents = events.filter(e => {
    const matchesSearch = e.message.toLowerCase().includes(searchTerm.toLowerCase()) || 
                         e.metadata.product.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSeverity = filterSeverity === "All" || e.severity === filterSeverity;
    return matchesSearch && matchesSeverity;
  });

  return (
    <div className="p-6 space-y-6 bg-slate-950 min-h-screen text-slate-200 font-inter">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent flex items-center gap-3">
            <Shield className="w-8 h-8 text-blue-500" />
            Threat Intelligence & SIEM
          </h1>
          <p className="text-slate-400 mt-1">Unified OCSF-Normalized Security Event Stream</p>
        </div>
        <button 
          onClick={fetchSIEMData}
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 border border-slate-800 rounded-lg hover:bg-slate-800 transition-all text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh Data
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-4 bg-slate-900/50 border border-slate-800 rounded-xl backdrop-blur-sm">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-slate-400 text-xs uppercase tracking-wider font-semibold">Total Events</p>
              <h3 className="text-2xl font-bold mt-1">{summary?.total_events || 0}</h3>
            </div>
            <Activity className="w-5 h-5 text-blue-500" />
          </div>
          <div className="mt-4 h-1 bg-slate-800 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 w-3/4 shadow-[0_0_10px_rgba(59,130,246,0.5)]" />
          </div>
        </div>

        {["Critical", "High", "Medium"].map((sev) => (
          <div key={sev} className="p-4 bg-slate-900/50 border border-slate-800 rounded-xl backdrop-blur-sm">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-slate-400 text-xs uppercase tracking-wider font-semibold">{sev} Alerts</p>
                <h3 className="text-2xl font-bold mt-1 text-slate-100">{summary?.severity_counts?.[sev] || 0}</h3>
              </div>
              <AlertTriangle className={`w-5 h-5 ${sev === 'Critical' ? 'text-red-500' : sev === 'High' ? 'text-orange-500' : 'text-yellow-500'}`} />
            </div>
          </div>
        ))}
      </div>

      {/* Main Analysis Area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Feed */}
        <div className="lg:col-span-2 bg-slate-900/50 border border-slate-800 rounded-2xl overflow-hidden flex flex-col">
          <div className="p-4 border-b border-slate-800 flex flex-col sm:flex-row gap-4 justify-between items-center bg-slate-900/80">
            <div className="relative w-full max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input 
                type="text" 
                placeholder="Search events, sources, actors..."
                className="w-full pl-10 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-sm focus:outline-none focus:border-blue-500 transition-colors"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="flex gap-2 w-full sm:w-auto">
              <select 
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
                className="px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="All">All Severities</option>
                <option value="Critical">Critical</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
              </select>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto max-h-[600px] scrollbar-thin scrollbar-thumb-slate-700">
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-slate-900 text-slate-400 text-xs uppercase tracking-wider z-10">
                <tr>
                  <th className="px-6 py-4 font-semibold">Time / Source</th>
                  <th className="px-6 py-4 font-semibold">Activity</th>
                  <th className="px-6 py-4 font-semibold text-center">Severity</th>
                  <th className="px-6 py-4 font-semibold">Entity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredEvents.length > 0 ? filteredEvents.map((event) => (
                  <tr key={event.id} className="hover:bg-slate-800/30 transition-colors group">
                    <td className="px-6 py-4">
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-slate-200">
                          {new Date(event.time).toLocaleTimeString()}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono uppercase">
                          {event.metadata.product}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4max-w-xs">
                      <p className="text-sm font-semibold text-slate-300 truncate">{event.class_name}</p>
                      <p className="text-xs text-slate-500 truncate mt-0.5">{event.message}</p>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${getSeverityColor(event.severity)}`}>
                        {event.severity.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center text-slate-400 group-hover:bg-blue-500/10 group-hover:text-blue-400 transition-colors">
                          <User className="w-4 h-4" />
                        </div>
                        <span className="text-xs text-slate-400 italic">
                          {event.actor?.user?.name || "System Process"}
                        </span>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={4} className="px-6 py-20 text-center text-slate-500 italic">
                      No security events found matching criteria.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Column: Insights */}
        <div className="space-y-6">
          <div className="p-6 bg-slate-900/50 border border-slate-800 rounded-2xl backdrop-blur-md">
            <h4 className="text-sm font-bold text-slate-100 flex items-center gap-2 mb-4 uppercase tracking-widest">
              <Filter className="w-4 h-4 text-blue-500" />
              Source Distribution
            </h4>
            <div className="space-y-4">
              {Object.entries(summary?.source_counts || {}).map(([source, count], idx) => {
                const total = summary?.total_events || 1;
                const percentage = Math.round((count as number / total) * 100);
                return (
                  <div key={source} className="space-y-2">
                    <div className="flex justify-between text-xs font-semibold">
                      <span className="text-slate-300">{source.toUpperCase()}</span>
                      <span className="text-slate-500">{count as number} events ({percentage}%)</span>
                    </div>
                    <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className={`h-full bg-gradient-to-r ${
                          ['from-blue-500 to-indigo-500', 'from-purple-500 to-pink-500', 'from-emerald-500 to-teal-500'][idx % 3]
                        }`}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="p-6 bg-slate-900/50 border border-slate-800 rounded-2xl backdrop-blur-md">
            <h4 className="text-sm font-bold text-slate-100 flex items-center gap-2 mb-4 uppercase tracking-widest">
              <Shield className="w-4 h-4 text-indigo-500" />
              Normalization Status
            </h4>
            <div className="space-y-4">
              <div className="p-4 bg-slate-950 border border-slate-800/50 rounded-xl flex items-center gap-4">
                <div className="p-2 bg-indigo-500/10 rounded-lg">
                  <Database className="w-6 h-6 text-indigo-400" />
                </div>
                <div>
                  <p className="text-xs text-slate-500">Schema Version</p>
                  <p className="text-lg font-bold text-slate-200 italic font-mono">OCSF 1.1.0-RC</p>
                </div>
              </div>
              <p className="text-[11px] text-slate-500 leading-relaxed bg-slate-800/20 p-3 rounded-lg border border-slate-800/50">
                All raw logs are being automatically mapped to the Open Cybersecurity Schema Framework. This ensures cross-product compatibility and standardized threat hunting.
              </p>
              <button className="w-full py-2.5 text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors flex items-center justify-center gap-1 border border-indigo-500/20 rounded-lg hover:bg-indigo-500/5">
                View Schema Documentation <ExternalLink className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ThreatDashboard;
