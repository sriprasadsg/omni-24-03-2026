/**
 * Shared fixtures for the Needs your decision tests (83-19): the card payload of 83-18, a routed authFetch and the
 * render helpers. The test files declare the vi.mock calls for apiService and the toast bus.
 */
import React from 'react';
import { vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { authFetch } from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsDecisions } from '../../components/AutonomousOpsDecisions';

export const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;
export const toast = showToast as unknown as ReturnType<typeof vi.fn>;

// ── fixtures ────────────────────────────────────────────────────────────────

export const MIN = 60_000;
export const HOUR = 60 * MIN;
export const at = (ms: number) => new Date(Date.now() + ms).toISOString();
export const clock = (iso: string) => new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

export function line(over: Record<string, unknown> = {}) {
  return {
    id: 'AO-1', state: 'awaiting_approval', bucket: 'pending', command: 'kill_process', label: 'Kill process',
    target: 'powershell.exe (PID 4120)', reason: 'A second source agreed this process is malicious.',
    ruleId: 'sweep:kill_process', consequenceText: 'Ends this process right away. Unsaved work in it is lost.',
    notice: null, result: null, needsPerson: true, createdAt: at(-5 * MIN), expiresAt: at(19 * HOUR + 30_000),
    revertsAt: null, chain: null, canApprove: true, canDeny: true, canConfirmIsolation: false,
    confirmedAt: null, confirmedBy: null,
    ...over,
  };
}

export function card(over: Record<string, unknown> = {}) {
  const actions = (over.actions as unknown[]) ?? [line()];
  return {
    id: 'INC-1', host: 'web-01', startedAt: at(-12 * MIN), alertCount: 1,
    deadlineAt: at(19 * HOUR + 30_000), deadlineKind: 'expires', actionCount: actions.length, actions,
    ...over,
  };
}

export const page = (items: unknown[], over: Record<string, unknown> = {}) =>
  ({ items, total: items.length, offset: 0, limit: 10, stopped: null, ...over });

export function isolated(over: Record<string, unknown> = {}) {
  return line({
    id: 'AO-ISO', state: 'verified', bucket: 'done', command: 'isolate_host', label: 'Isolate host', target: null,
    consequenceText: 'Confirming keeps this computer isolated until you restore it. Without it, the computer returns to the network automatically at {at}.',
    result: 'web-01 is isolated. The connection to the platform stays open.',
    expiresAt: null, revertsAt: at(3 * HOUR + 12 * MIN + 30_000), canApprove: false, canDeny: false, canConfirmIsolation: true,
    ...over,
  });
}

export const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

export function statusPayload(over: Record<string, unknown> = {}) {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto', previousLevel: null,
    shadow: { effective: false, source: null }, stop: { tenant: null, platform: null },
    canStop: true, canResume: true, canStopPlatform: false, canResumePlatform: false,
    ...over,
  };
}

export type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;
export interface Handlers { incidents?: Handler; decision?: Handler; status?: Handler; rollouts?: Handler; lineDecision?: Handler }

export function routeFetch(h: Handlers) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === '/api/autonomous-ops/status') return (h.status ?? (() => jsonRes(statusPayload())))(url, init);
    if (path === '/api/autonomous-ops/incidents') return (h.incidents ?? (() => jsonRes(page([]))))(url, init);
    // 84-15: the section reads rollout approval cards beside incidents; the default is an empty page.
    if (path === '/api/autonomous-ops/rollout-cards') return (h.rollouts ?? (() => jsonRes(page([]))))(url, init);
    if (/^\/api\/autonomous-ops\/rollout-lines\/[^/]+\/[^/]+\/[^/]+\/(approve|deny)$/.test(path)) {
      return (h.lineDecision ?? (() => jsonRes({}, 500)))(url, init);
    }
    if (/^\/api\/autonomous-ops\/actions\/[^/]+\/(approve|deny|confirm-isolation)$/.test(path)) {
      return (h.decision ?? (() => jsonRes({}, 500)))(url, init);
    }
    throw new Error(`unexpected request ${url}`);
  });
}

export const callsTo = (re: RegExp) => mockAuthFetch.mock.calls.filter(c => re.test((c[0] as string).split('?')[0]));
export const incidentCalls = () => callsTo(/\/incidents$/);
export const rolloutCalls = () => callsTo(/\/rollout-cards$/);
export const lineCalls = () => callsTo(/\/rollout-lines\//);
export const decisionCalls = () => callsTo(/\/(approve|deny|confirm-isolation)$/);

export function view(props: { onDecisionIds?: (ids: ReadonlySet<string>) => void; onDecided?: () => void; refreshSignal?: number } = {}) {
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'pat@example.com', role: 'Tenant Admin', tenantId: 'tenant-a', permissions: [] } as any,
      login: async () => false, logout: () => {}, signup: async () => false, registerTenant: async () => false,
      hasPermission: () => true, enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={null} enabled>
        <AutonomousOpsDecisions tenantId={null} {...props} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}

export async function shown(props: Parameters<typeof view>[0] = {}) {
  const out = render(view(props));
  await screen.findByRole('heading', { name: 'Needs your decision' });
  return out;
}

export const flush = () => act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });

