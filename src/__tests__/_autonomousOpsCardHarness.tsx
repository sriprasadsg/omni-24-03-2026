/** Shared fixtures for the Autonomous Ops status card tests (81-10). The test file registers the vi.mock calls. */
import React from 'react';
import { authFetch } from '../../services/apiService';
import { UserContext } from '../../contexts/UserContext';
import { AutonomousOpsStatusProvider } from '../../contexts/AutonomousOpsStatusContext';
import { AutonomousOpsStatusCard } from '../../components/AutonomousOpsStatusCard';

export const mockAuthFetch = authFetch as unknown as ReturnType<typeof import('vitest').vi.fn>;

// ── fixtures ────────────────────────────────────────────────────────────────

export const AT = '2026-10-25T14:32:00Z';
export const stopView = (over: Record<string, unknown> = {}) =>
  ({ scope: 'tenant', by: 'Dana Admin', at: AT, reason: 'Investigating a bad rule', ...over });
export const platformStopView = (over: Record<string, unknown> = {}) =>
  stopView({ scope: 'platform', by: 'Platform administrator', reason: null, ...over });

export function statusPayload(over: Record<string, unknown> = {}) {
  return {
    tenantId: 'tenant-a', tenantName: 'Acme Corp', scope: 'tenant', platformTenant: false,
    eligible: true, levelReadable: true, level: 'undoable_auto', maxLevel: 'undoable_auto',
    previousLevel: null, shadow: { effective: false, source: null },
    stop: { tenant: null, platform: null },
    canStop: true, canResume: false, canStopPlatform: false, canResumePlatform: false,
    ...over,
  };
}

export function platformStatusPayload(over: Record<string, unknown> = {}) {
  return {
    scope: 'platform', stop: { platform: null }, tenantStopsCount: 2,
    canStopPlatform: true, canResumePlatform: false, ...over,
  };
}

export const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

export const TENANT_ADMIN = ['view:autonomous_ops', 'control:autonomous_ops', 'manage:autonomous_ops'];
export const SECURITY_ANALYST = ['view:autonomous_ops', 'control:autonomous_ops'];
export const ANALYST = ['view:autonomous_ops'];
export const SUPER = [...TENANT_ADMIN, 'control:platform_autonomous_ops'];

export type Handler = (init: RequestInit) => Response | Promise<Response>;
export interface Routes {
  status?: Handler; platformStatus?: Handler;
  stop?: Handler; resume?: Handler; platformStop?: Handler; platformResume?: Handler;
}

export function route(r: Routes) {
  const ok = (h: Handler | undefined, fallback: () => Response) => (init: RequestInit) => (h ? h(init) : fallback());
  mockAuthFetch.mockImplementation(async (url: string, init: RequestInit = {}) => {
    const path = url.split('?')[0];
    switch (path) {
      case '/api/autonomous-ops/status': return ok(r.status, () => jsonRes(statusPayload()))(init);
      case '/api/platform/autonomous-ops/status': return ok(r.platformStatus, () => jsonRes(platformStatusPayload()))(init);
      case '/api/autonomous-ops/stop': return ok(r.stop, () => jsonRes(statusPayload()))(init);
      case '/api/autonomous-ops/resume': return ok(r.resume, () => jsonRes(statusPayload()))(init);
      case '/api/platform/autonomous-ops/stop': return ok(r.platformStop, () => jsonRes(platformStatusPayload()))(init);
      case '/api/platform/autonomous-ops/resume': return ok(r.platformResume, () => jsonRes(platformStatusPayload()))(init);
      default: throw new Error(`unexpected request ${url}`);
    }
  });
}

export const posts = (path: string) =>
  mockAuthFetch.mock.calls.filter(c => (c[1] as RequestInit | undefined)?.method === 'POST' && (c[0] as string).split('?')[0] === path);

export function card(permissions: string[], opts: { role?: string; tenantId?: string | null; enabled?: boolean } = {}) {
  const { role = 'Tenant Admin', tenantId = null, enabled = true } = opts;
  return (
    <UserContext.Provider value={{
      currentUser: { id: 'u1', name: 'Pat', email: 'p@example.com', role, tenantId: 'tenant-a', permissions } as any,
      login: async () => false, logout: () => {}, signup: async () => false,
      registerTenant: async () => false,
      hasPermission: (p: any) => permissions.includes(p),
      enabledFeatures: [], serverLockedFeatures: {},
    }}>
      <AutonomousOpsStatusProvider tenantId={tenantId} enabled={enabled}>
        <AutonomousOpsStatusCard tenantId={tenantId} />
      </AutonomousOpsStatusProvider>
    </UserContext.Provider>
  );
}


export const stoppedTenant = (over: Record<string, unknown> = {}) =>
  statusPayload({ stop: { tenant: stopView(), platform: null }, canResume: true, ...over });

