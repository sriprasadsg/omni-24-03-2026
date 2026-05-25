import React, { useState, useEffect, useCallback } from 'react';
import { Box, Shield, AlertTriangle, RefreshCw, Search, ChevronDown, ChevronRight } from 'lucide-react';

interface ContainerImage {
  id: string;
  image: string;
  tag: string;
  registry: string;
  os: string;
  status: string;
  scanned_at: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  total: number;
}

interface Vuln {
  id: string;
  image_id: string;
  cve: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  cvss: number;
  package: string;
  installed_version: string;
  fixed_version: string;
  description: string;
}

interface ContainerStats {
  images_scanned: number;
  critical_cves: number;
  high_cves: number;
  images_with_critical: number;
  base_images_outdated: number;
  os_vulns: number;
  library_vulns: number;
}

const SEV_COLOR: Record<string, string> = {
  CRITICAL: '#fca5a5', HIGH: '#fcd34d', MEDIUM: '#a5b4fc', LOW: '#94a3b8',
};

function timeAgo(ts: number) {
  const d = Date.now() / 1000 - ts;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

export function ContainerScanDashboard() {
  const [images, setImages] = useState<ContainerImage[]>([]);
  const [vulns, setVulns] = useState<Vuln[]>([]);
  const [stats, setStats] = useState<ContainerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ContainerImage | null>(null);
  const [search, setSearch] = useState('');

  const token = sessionStorage.getItem('access_token');
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  const fetchAll = useCallback(async () => {
    setLoading(true);
    const [imgs, v, s] = await Promise.all([
      fetch('/api/container-scan/images', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/container-scan/vulnerabilities', { headers }).then(r => r.ok ? r.json() : []),
      fetch('/api/container-scan/stats', { headers }).then(r => r.ok ? r.json() : null),
    ]).catch(() => [[], [], null]);
    setImages(Array.isArray(imgs) ? imgs : []);
    setVulns(Array.isArray(v) ? v : []);
    setStats(s);
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const filteredImages = images.filter(img =>
    !search || img.image.toLowerCase().includes(search.toLowerCase()) || img.registry.toLowerCase().includes(search.toLowerCase())
  );

  const selectedVulns = selected ? vulns.filter(v => v.image_id === selected.id) : [];

  return (
    <div style={{ padding: '28px 32px', color: '#f1f5f9', fontFamily: 'Inter, sans-serif', minHeight: '100vh', background: '#040812' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: '0.72em', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#6366f1', marginBottom: 6 }}>DevSecOps</div>
          <h1 style={{ fontSize: '1.8em', fontWeight: 900, letterSpacing: '-0.03em', margin: 0 }}>Container Image Scanning</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.85em', marginTop: 4 }}>CVE detection across all container registries — ECR · Docker Hub · GCR · ACR</p>
        </div>
        <button onClick={fetchAll} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(99,102,241,.15)', border: '1px solid rgba(99,102,241,.3)', color: '#a5b4fc', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: '0.82em' }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 14, marginBottom: 28 }}>
          {[
            { label: 'Images Scanned', value: stats.images_scanned, color: '#a5b4fc' },
            { label: 'Critical CVEs', value: stats.critical_cves, color: '#fca5a5' },
            { label: 'High CVEs', value: stats.high_cves, color: '#fcd34d' },
            { label: 'w/ Critical', value: stats.images_with_critical, color: '#fca5a5' },
            { label: 'Outdated Base', value: stats.base_images_outdated, color: '#fcd34d' },
            { label: 'OS Vulns', value: stats.os_vulns, color: '#a5b4fc' },
            { label: 'Lib Vulns', value: stats.library_vulns, color: '#94a3b8' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 12, padding: '16px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.8em', fontWeight: 900, color }}>{value}</div>
              <div style={{ fontSize: '0.72em', color: '#94a3b8', marginTop: 4 }}>{label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: 20 }}>
        {/* Image list */}
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)', display: 'flex', gap: 12, alignItems: 'center' }}>
            <Search size={14} color="#94a3b8" />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search images…"
              style={{ background: 'none', border: 'none', color: '#f1f5f9', fontSize: '0.88em', outline: 'none', flex: 1 }} />
          </div>
          {loading ? <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading…</div> : (
            filteredImages.map(img => (
              <div key={img.id} onClick={() => setSelected(img === selected ? null : img)}
                style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 16, padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.04)', cursor: 'pointer', background: selected?.id === img.id ? 'rgba(99,102,241,.08)' : 'transparent', alignItems: 'center' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                    <Box size={13} color="#6366f1" />
                    <span style={{ fontWeight: 600, fontSize: '0.88em' }}>{img.image}:{img.tag}</span>
                  </div>
                  <div style={{ fontSize: '0.72em', color: '#64748b' }}>{img.registry} · {img.os} · {timeAgo(img.scanned_at)}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, fontSize: '0.72em', fontWeight: 700 }}>
                  {img.critical > 0 && <span style={{ color: '#fca5a5', background: 'rgba(239,68,68,.1)', borderRadius: 20, padding: '2px 8px' }}>C:{img.critical}</span>}
                  {img.high > 0 && <span style={{ color: '#fcd34d', background: 'rgba(245,158,11,.1)', borderRadius: 20, padding: '2px 8px' }}>H:{img.high}</span>}
                  <span style={{ color: '#94a3b8', background: 'rgba(255,255,255,.05)', borderRadius: 20, padding: '2px 8px' }}>{img.total} total</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Vuln detail */}
        <div style={{ background: 'rgba(255,255,255,.04)', border: '1px solid rgba(255,255,255,.08)', borderRadius: 14, overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid rgba(255,255,255,.07)' }}>
            <span style={{ fontWeight: 700, fontSize: '0.9em' }}>{selected ? `CVEs — ${selected.image}:${selected.tag}` : 'Select an image'}</span>
          </div>
          <div style={{ maxHeight: 500, overflowY: 'auto', padding: 12 }}>
            {!selected ? (
              <div style={{ textAlign: 'center', color: '#94a3b8', padding: 40, fontSize: '0.85em' }}>Click an image to view CVEs</div>
            ) : selectedVulns.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#6ee7b7', padding: 40, fontSize: '0.85em' }}>No CVEs found for this image</div>
            ) : selectedVulns.map(v => (
              <div key={v.id} style={{ background: 'rgba(255,255,255,.03)', border: `1px solid ${SEV_COLOR[v.severity]}25`, borderRadius: 10, padding: '12px 14px', marginBottom: 10 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: '0.7em', fontWeight: 700, color: SEV_COLOR[v.severity], background: `${SEV_COLOR[v.severity]}15`, borderRadius: 20, padding: '2px 8px' }}>{v.severity}</span>
                  <span style={{ fontFamily: 'monospace', fontSize: '0.8em', fontWeight: 700, color: '#a5b4fc' }}>{v.cve}</span>
                  <span style={{ marginLeft: 'auto', fontSize: '0.72em', color: '#94a3b8' }}>CVSS {v.cvss}</span>
                </div>
                <div style={{ fontSize: '0.78em', color: '#94a3b8', marginBottom: 4 }}>
                  <strong style={{ color: '#f1f5f9' }}>{v.package}</strong> {v.installed_version} → fix: {v.fixed_version}
                </div>
                <div style={{ fontSize: '0.72em', color: '#64748b', lineHeight: 1.4 }}>{v.description}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ContainerScanDashboard;
