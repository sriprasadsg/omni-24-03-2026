/**
 * Shared set-up for the Service desk card tests (85-16): the view fixture, a routed authFetch for the three desk routes,
 * and a render helper. authFetch and the toast are mocked by each test file with vi.mock; nothing here reaches a real API.
 */
import React from 'react';
import { expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { authFetch } from '../../services/apiService';
import { DeskSettingsCard } from '../../components/serviceDesk/DeskSettingsCard';

export type Json = Record<string, any>;
export type Reply = Response | Promise<Response>;

export const mockAuthFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

export const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

export const DESK_URL = '/api/autonomous-ops/service-desk';
export const RESTORE_URL = `${DESK_URL}/restore`;

export const view = (over: Json = {}): Json => ({
  mode: 'drafts', effectiveMode: 'drafts', readable: true, screensOn: true, words: [], maxWords: 50, breaker: null,
  posting: { posting: false, blockers: [] }, model: { state: 'online', tag: 'llama3.2:3b' },
  timing: { medianSeconds: 100, samples: 12, measured: true }, canManage: true, canRestore: false,
  ...over,
});

export const BREAKER = { trippedAt: '2026-11-08T10:00:00Z', count: 3 };

export const ALL_BLOCKERS = [
  { code: 'level', level: 'suggest' }, { code: 'shadow' }, { code: 'stop' }, { code: 'hourly_limit' }, { code: 'desk_breaker' },
];

export let stored: Json = view();
export const setStored = (v: Json) => { stored = v; };

interface Routes {
  get?: () => Reply;
  put?: (body: Json) => Reply;
  restore?: () => Reply;
}

/** GET returns what is stored; PUT merges the body into it (mode also becomes effectiveMode); restore clears the breaker and sets post. */
export function routeDesk(opts: Routes = {}) {
  mockAuthFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0];
    if (path === DESK_URL && !init?.method) return (opts.get ?? (() => jsonRes(stored)))();
    if (path === DESK_URL && init?.method === 'PUT') {
      const body = JSON.parse(init.body as string) as Json;
      return (opts.put ?? ((b: Json) => {
        stored = { ...stored, ...b, ...(b.mode ? { effectiveMode: b.mode } : {}) };
        return jsonRes(stored);
      }))(body);
    }
    if (path === RESTORE_URL && init?.method === 'POST') {
      return (opts.restore ?? (() => {
        stored = { ...stored, breaker: null, mode: 'post', effectiveMode: 'post', canRestore: false };
        return jsonRes(stored);
      }))();
    }
    throw new Error(`unexpected request ${url}`);
  });
}

export const puts = () => mockAuthFetch.mock.calls.filter(c => (c[1] as RequestInit | undefined)?.method === 'PUT');
export const putBodies = () => puts().map(c => JSON.parse((c[1] as RequestInit).body as string));
export const posts = () => mockAuthFetch.mock.calls.filter(c => (c[1] as RequestInit | undefined)?.method === 'POST');
export const gets = () => mockAuthFetch.mock.calls.filter(c => !(c[1] as RequestInit | undefined)?.method);

export const header = () => screen.getByRole('button', { name: 'Service desk' });
export const saveButton = () => screen.getByRole('button', { name: /^(Save service desk settings|Saving\.\.\.)$/ });

/** Renders the card, waits for the first read, and (by default) opens it. */
export async function openCard(over: Json = {}, opts: Routes = {}, expand = true) {
  stored = view(over);
  routeDesk(opts);
  const out = render(<DeskSettingsCard tenantId={null} />);
  await waitFor(() => expect(out.container.querySelector('.h-4.w-64')).toBeNull());
  if (expand) {
    fireEvent.click(header());
    await screen.findByRole('radiogroup', { name: 'Answers to requesters' });
  }
  return out;
}
