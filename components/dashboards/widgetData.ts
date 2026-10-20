import { authFetch } from '../../services/apiService';

/**
 * One loader per catalogue widget (shared/dashboard-widgets.json). Each reads an existing
 * catalogue API directly, so a refused or failed request shows as an error in the widget
 * instead of cached or demo data.
 */

export type Severity = 'Critical' | 'High' | 'Medium' | 'Low';

export type WidgetData =
  | { kind: 'kpi'; value: number; unit?: '%'; sub?: string }
  | { kind: 'bar'; items: { label: string; value: number; severity?: Severity }[]; max?: number; unit?: '%' }
  | { kind: 'table'; columns: string[]; numeric?: number[]; rows: (string | number)[][] }
  | { kind: 'list'; items: { primary: string; secondary?: string; when?: string }[] };

export class WidgetLoadError extends Error {
  constructor(readonly status: number) {
    super(status === 403 ? "Your role can't read this data" : `Couldn't load (${status || 'network error'})`);
  }
}

async function getJson(url: string): Promise<any> {
  let res: Response;
  try {
    res = await authFetch(url);
  } catch {
    throw new WidgetLoadError(0);
  }
  if (!res.ok) throw new WidgetLoadError(res.status);
  return res.json();
}

const list = (data: any, key = 'items'): any[] =>
  Array.isArray(data) ? data : Array.isArray(data?.[key]) ? data[key] : [];

const lower = (v: unknown) => String(v ?? '').trim().toLowerCase();

const CLOSED = new Set(['resolved', 'closed', 'dismissed', 'done', 'mitigated', 'false_positive', 'false positive']);
const isOpen = (status: unknown) => !CLOSED.has(lower(status));

export function severityOf(raw: unknown): Severity | null {
  const s = lower(raw);
  if (s.startsWith('crit')) return 'Critical';
  if (s.startsWith('high') || s === 'serious' || s === 'important') return 'High';
  if (s.startsWith('med') || s === 'moderate' || s === 'warning') return 'Medium';
  if (s.startsWith('low') || s.startsWith('info')) return 'Low';
  return null;
}

const SEVERITIES: Severity[] = ['Critical', 'High', 'Medium', 'Low'];

function bySeverity(records: any[], field = 'severity'): WidgetData {
  const counts: Record<Severity, number> = { Critical: 0, High: 0, Medium: 0, Low: 0 };
  for (const r of records) {
    const sev = severityOf(r?.[field]);
    if (sev) counts[sev] += 1;
  }
  return { kind: 'bar', items: SEVERITIES.map(s => ({ label: s, value: counts[s], severity: s })) };
}

/** Counts per label, biggest first; past `top` labels the rest fold into "Other". */
export function groupCounts(labels: string[], top = 6): { label: string; value: number }[] {
  const counts = new Map<string, number>();
  for (const label of labels) counts.set(label, (counts.get(label) || 0) + 1);
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const head = sorted.slice(0, top).map(([label, value]) => ({ label, value }));
  const rest = sorted.slice(top).reduce((n, [, v]) => n + v, 0);
  return rest ? [...head, { label: 'Other', value: rest }] : head;
}

const shortDate = (iso: unknown) => {
  const t = Date.parse(String(iso ?? ''));
  return Number.isNaN(t) ? '—' : new Date(t).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

const osFamily = (asset: any) => {
  const name = String(asset?.osName || asset?.os || asset?.platform || '').trim();
  if (!name) return 'Unknown';
  // "Microsoft Windows 11 Pro" -> "Windows 11", "Ubuntu 24.04.1 LTS" -> "Ubuntu 24.04"
  const m = name.replace(/^Microsoft\s+/i, '').match(/^([A-Za-z][A-Za-z ]*?)\s*(\d+(?:\.\d+)?)?/);
  return m ? [m[1].trim(), m[2]].filter(Boolean).join(' ') : name;
};

export const WIDGET_LOADERS: Record<string, () => Promise<WidgetData>> = {
  'agents-status': async () => {
    const agents = list(await getJson('/api/agents'));
    const online = agents.filter(a => lower(a?.status) === 'online').length;
    return { kind: 'kpi', value: online, sub: `of ${agents.length} agent${agents.length === 1 ? '' : 's'}` };
  },
  'agents-by-platform': async () => {
    const agents = list(await getJson('/api/agents'));
    return { kind: 'bar', items: groupCounts(agents.map(a => String(a?.platform || a?.os || 'Unknown'))) };
  },
  'assets-total': async () => {
    const assets = list(await getJson('/api/assets'));
    return { kind: 'kpi', value: assets.length, sub: 'tracked assets' };
  },
  'assets-by-os': async () => {
    const assets = list(await getJson('/api/assets'));
    return { kind: 'bar', items: groupCounts(assets.map(osFamily)) };
  },
  'os-patches-pending': async () => {
    const data = await getJson('/api/patches/os');
    const assets = list(data, 'assets');
    return { kind: 'kpi', value: Number(data?.total_pending_os_patches) || 0,
             sub: `across ${assets.length} asset${assets.length === 1 ? '' : 's'}` };
  },
  'patch-jobs': async () => {
    const jobs = list(await getJson('/api/patches/deployment-jobs'))
      .sort((a, b) => String(b?.createdAt || b?.startTime || '').localeCompare(String(a?.createdAt || a?.startTime || '')))
      .slice(0, 6);
    return { kind: 'table', columns: ['Started', 'Status', 'Patches'], numeric: [2],
             rows: jobs.map(j => [shortDate(j?.createdAt || j?.startTime), String(j?.status || '—'),
                                  (j?.patchIds || j?.targetPatchIds || []).length]) };
  },
  'vulns-by-severity': async () => {
    const stats = await getJson('/api/vulnerabilities/stats');
    return { kind: 'bar', items: SEVERITIES.map(s => ({ label: s, value: Number(stats?.[s]) || 0, severity: s })) };
  },
  'compliance-score': async () => {
    const score = await getJson('/api/compliance/score');
    const frameworks = list(score, 'frameworks');
    return { kind: 'kpi', value: Math.round(Number(score?.overall_score) || 0), unit: '%',
             sub: `${frameworks.length} framework${frameworks.length === 1 ? '' : 's'}` };
  },
  'compliance-frameworks': async () => {
    const frameworks = list(await getJson('/api/compliance/score'), 'frameworks');
    return { kind: 'bar', unit: '%', max: 100,
             items: frameworks.slice(0, 8).map(f => ({ label: String(f?.short_name || f?.framework_name || f?.framework_id),
                                                    value: Math.round(Number(f?.score) || 0) })) };
  },
  'alerts-open': async () => {
    const open = list(await getJson('/api/alerts')).filter(a => isOpen(a?.status));
    const critical = open.filter(a => severityOf(a?.severity) === 'Critical').length;
    return { kind: 'kpi', value: open.length, sub: `${critical} critical` };
  },
  'alerts-by-severity': async () => bySeverity(list(await getJson('/api/alerts')).filter(a => isOpen(a?.status))),
  'cases-open': async () => {
    const open = list(await getJson('/api/security-cases')).filter(c => isOpen(c?.status));
    return { kind: 'kpi', value: open.length, sub: 'open cases' };
  },
  'cloud-findings': async () => bySeverity(list(await getJson('/api/cspm/findings')).filter(f => isOpen(f?.status))),
  'top-risks': async () => {
    const risks = list(await getJson('/api/risks'))
      .sort((a, b) => (Number(b?.risk_score) || 0) - (Number(a?.risk_score) || 0)).slice(0, 6);
    return { kind: 'table', columns: ['Risk', 'Score', 'Status'], numeric: [1],
             rows: risks.map(r => [String(r?.title || '—'), Number(r?.risk_score) || 0, String(r?.status || '—')]) };
  },
  'tickets-open': async () => {
    const data = await getJson('/api/tickets?status=open&page_size=1');
    return { kind: 'kpi', value: Number(data?.total) || 0, sub: 'open tickets' };
  },
  'audit-recent': async () => {
    const entries = list(await getJson('/api/audit-logs?limit=8'));
    return { kind: 'list', items: entries.map(e => ({
      primary: String(e?.action || e?.details || 'Activity'),
      secondary: String((typeof e?.actor === 'object' ? e.actor?.email : e?.actor) || e?.userName || e?.user || ''),
      when: shortDate(e?.timestamp),
    })) };
  },
};
