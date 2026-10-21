/**
 * Security Operations screen:
 *  - VirusTotal lookups post `artifact_type` (the backend refused `type` with 422) and a failed lookup
 *    reports the server's reason instead of a stand-in "Unknown" verdict that was stored on the case.
 *  - The threat-intel feed maps the API's snake_case fields (rows showed "undefined" / "Invalid Date").
 *  - Enable/Disable on a playbook shows the state the server answered with.
 *  - The 24-hour tile counts the last 24 hours; events that load after mount can be inspected.
 *  - A disabled playbook is marked, cannot be run, and is skipped by "Run playbook" on an event.
 *  - Empty events, lookups and playbooks say so.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { SecurityDashboard } from '../../components/SecurityDashboard';
import { scanArtifactWithVirusTotal, fetchThreatIntelFeed } from '../../services/apiService';
import { UserContext } from '../../contexts/UserContext';
import { TimeZoneProvider } from '../../contexts/TimeZoneContext';
import { showToast } from '../../utils/toast';
import type { SecurityCase, SecurityEvent, Playbook } from '../../types';

const json = (body: unknown, status = 200) =>
  ({ ok: status >= 200 && status < 300, status, headers: new Headers(), json: async () => body }) as Response;

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

const recent: SecurityEvent = {
  id: 'ev-1', tenantId: 't', timestamp: hoursAgo(1), severity: 'Critical', description: 'Mimikatz detected',
  type: 'Malware', source: { ip: '203.0.113.9', hostname: 'host-a' },
};
const old: SecurityEvent = {
  id: 'ev-2', tenantId: 't', timestamp: hoursAgo(72), severity: 'High', description: 'Brute force',
  type: 'Auth', source: { ip: '198.51.100.4', hostname: 'host-b' },
};
const openCase: SecurityCase = {
  id: 'case-1', tenantId: 't', title: 'Case: Mimikatz detected', status: 'New', severity: 'Critical', owner: 'Ava',
  createdAt: hoursAgo(1), updatedAt: hoursAgo(1), relatedEvents: [recent], comments: [], enrichmentData: [],
};
const playbook: Playbook = {
  id: 'pb-1', name: 'Isolate host', description: 'Cut the host off', trigger: 'Critical malware', source: 'User',
  conditions: [], steps: [],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  vi.mocked(showToast).mockReset();
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function renderScreen(overrides: Partial<React.ComponentProps<typeof SecurityDashboard>> = {}) {
  const props: React.ComponentProps<typeof SecurityDashboard> = {
    securityCases: [openCase], playbooks: [playbook], securityEvents: [recent, old], users: [],
    onCaseUpdate: vi.fn(async c => c), onGeneratePlaybook: vi.fn(), onAnalyzeImpact: vi.fn(), threatIntelFeed: [],
    ...overrides,
  };
  const user = { id: 'u', name: 'Ava', email: 'ava@x.test', role: 'Tenant Admin', tenantId: 't' } as any;
  const ui = (p: typeof props) => (
    <TimeZoneProvider>
      <UserContext.Provider value={{ currentUser: user, hasPermission: () => true } as any}>
        <SecurityDashboard {...p} />
      </UserContext.Provider>
    </TimeZoneProvider>
  );
  const view = render(ui(props));
  return { ...view, props, rerenderWith: (more: Partial<typeof props>) => view.rerender(ui({ ...props, ...more })) };
}

const tile = (label: string) => screen.getByRole('group', { name: label });

describe('VirusTotal lookups', () => {
  it('posts artifact_type and maps the snake_case answer', async () => {
    fetchMock.mockResolvedValue(json({
      id: 'scan-1', artifact: '203.0.113.9', artifact_type: 'ip', verdict: 'Malicious', detection_ratio: '12/90',
      scan_date: '2026-10-21T06:00:00Z', created_at: '2026-10-21T06:00:00Z',
    }));
    const result = await scanArtifactWithVirusTotal('203.0.113.9', 'ip');
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/threat-intel/scan');
    expect(JSON.parse(opts.body)).toEqual({ artifact: '203.0.113.9', artifact_type: 'ip' });
    expect(result).toMatchObject({ id: 'scan-1', artifactType: 'ip', verdict: 'Malicious', detectionRatio: '12/90', scanDate: '2026-10-21T06:00:00Z' });
  });

  it("throws the server's reason instead of returning a stand-in verdict", async () => {
    fetchMock.mockResolvedValue(json({ detail: 'VirusTotal is not configured. Set VIRUSTOTAL_API_KEY on the backend to enable threat-intel scanning.' }, 503));
    await expect(scanArtifactWithVirusTotal('203.0.113.9', 'ip')).rejects.toThrow(/VIRUSTOTAL_API_KEY/);
  });

  it('maps feed rows from snake_case', async () => {
    fetchMock.mockResolvedValue(json([{ id: 's1', artifact: 'evil.test', artifact_type: 'domain', verdict: 'Suspicious', detection_ratio: '3/90', scan_date: '2026-10-20T10:00:00Z' }]));
    expect(await fetchThreatIntelFeed()).toEqual([{
      id: 's1', artifact: 'evil.test', artifactType: 'domain', source: 'VirusTotal', verdict: 'Suspicious',
      detectionRatio: '3/90', scanDate: '2026-10-20T10:00:00Z', reportUrl: '',
    }]);
  });

  it('a failed scan says why and leaves the case untouched', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'VirusTotal is not configured.' }, 503));
    const { props } = renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Scan IP/ }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(expect.stringContaining('VirusTotal is not configured.'), 'error'));
    expect(props.onCaseUpdate).not.toHaveBeenCalled();
  });

  it('a lookup made here opens its report and joins the feed', async () => {
    fetchMock.mockResolvedValue(json({ id: 'scan-2', artifact: '203.0.113.9', artifact_type: 'ip', verdict: 'Harmless', detection_ratio: '0/90', scan_date: hoursAgo(0) }));
    const { props } = renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Scan IP/ }));
    expect(await screen.findByText('Threat Intelligence Scan')).toBeTruthy();
    expect(screen.getAllByText('203.0.113.9').length).toBeGreaterThan(1);
    expect(props.onCaseUpdate).toHaveBeenCalledWith(expect.objectContaining({ enrichmentData: [expect.objectContaining({ id: 'scan-2' })] }));
  });
});

describe('Security Operations screen', () => {
  it('counts only the last 24 hours in the 24-hour tile', () => {
    renderScreen();
    expect(within(tile('Events, last 24 hours')).getByText('1')).toBeTruthy();
    expect(within(tile('Events, last 24 hours')).queryByText('2')).toBeNull();
  });

  it('shows the details of events that load after mount', () => {
    const { rerenderWith } = renderScreen({ securityEvents: [] });
    rerenderWith({ securityEvents: [recent, old] });
    expect(screen.getByRole('button', { name: /Scan IP/ })).toBeTruthy();
    expect(screen.getAllByText('Mimikatz detected').length).toBeGreaterThan(1);
  });

  it('Scan IP is off for an event without an IP', () => {
    renderScreen({ securityEvents: [{ ...recent, source: { ip: 'N/A', hostname: 'host-a' } }] });
    expect(screen.getByRole('button', { name: /Scan IP/ })).toBeDisabled();
  });

  it("Enable/Disable shows the server's answer", async () => {
    fetchMock.mockResolvedValue(json({ id: 'pb-1', enabled: false }));
    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Playbooks/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Disable' }));
    expect(await screen.findByRole('button', { name: 'Enable' })).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/playbooks/pb-1/toggle');
  });

  it('Run playbook from an event skips disabled playbooks', () => {
    const off: Playbook = { ...playbook, id: 'pb-0', name: 'Old sweep', enabled: false };
    renderScreen({ playbooks: [off, playbook] });
    fireEvent.click(screen.getByRole('button', { name: 'Run playbook' }));
    expect(screen.getByText('Isolate host')).toBeTruthy();
    expect(screen.queryByText('Old sweep')).toBeNull();
  });

  it('a disabled playbook is marked and cannot be run', () => {
    renderScreen({ playbooks: [{ ...playbook, enabled: false }] });
    fireEvent.click(screen.getByRole('button', { name: /Playbooks/ }));
    expect(screen.getByText('Disabled')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Run playbook' })).toBeDisabled();
  });

  it('says so when there are no events, lookups or playbooks', () => {
    renderScreen({ securityEvents: [], playbooks: [] });
    expect(screen.getByText('No security events')).toBeTruthy();
    expect(screen.getByText('No lookups yet')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Playbooks/ }));
    expect(screen.getByText('No playbooks yet')).toBeTruthy();
  });

  it('feed rows open their report', () => {
    const lookup = { id: 's1', artifact: 'evil.test', artifactType: 'domain' as const, source: 'VirusTotal', verdict: 'Suspicious' as const, detectionRatio: '3/90', scanDate: hoursAgo(2), reportUrl: '' };
    renderScreen({ threatIntelFeed: [lookup] });
    fireEvent.click(screen.getByRole('button', { name: 'Report for evil.test' }));
    expect(screen.getByText('Threat Intelligence Scan')).toBeTruthy();
  });

  it('a refused toggle keeps the state and says so', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'Not authorized' }, 403));
    renderScreen();
    fireEvent.click(screen.getByRole('button', { name: /Playbooks/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Disable' }));
    await waitFor(() => expect(showToast).toHaveBeenCalledWith(expect.stringContaining('Isolate host'), 'error'));
    expect(screen.getByRole('button', { name: 'Disable' })).toBeTruthy();
  });
});
