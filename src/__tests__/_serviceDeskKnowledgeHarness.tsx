/**
 * Shared set-up for the Knowledge Base desk tests (85-21): fixtures for the document list and its flags, and a routed
 * authFetch. Each test file mocks '../../services/apiService' and '../../utils/toast' with vi.mock; nothing here reaches a
 * real API. A request with no route fails loudly so a test never passes on a call it did not expect.
 */
import React from 'react';
import { expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { authFetch } from '../../services/apiService';
import KnowledgeBaseDashboard from '../../components/KnowledgeBaseDashboard';

export type Json = Record<string, any>;
export type Reply = Response | Promise<Response>;
export type Handler = (init?: RequestInit) => Reply;

export const mockFetch = authFetch as unknown as ReturnType<typeof vi.fn>;

export const jsonRes = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

export const kbDoc = (over: Json = {}): Json => ({
  id: 'kb-1', title: 'Printer fix', source: 'manual', tags: ['it'], createdAt: '2026-11-01T10:00:00Z',
  tenantId: 't1', helpdesk: false, starterKey: null, updatedAt: '2026-11-01T10:00:00Z', ...over,
});

export const kbFlags = (over: Json = {}): Json => ({
  canManageArticles: true, canSeeGaps: false, helpdeskCount: 0, starterMissing: 4, deskOff: false, ...over,
});

export const docList = (docs: Json[], flags: Json = kbFlags()) => jsonRes({ docs, count: docs.length, ...flags });

/** Route table: "METHOD /path" (query string included when the call has one) to a handler or a ready answer. */
export type Routes = Record<string, Handler | Response | Promise<Response>>;

export function serve(routes: Routes) {
  mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`;
    const hit = routes[key];
    if (hit === undefined) throw new Error(`unmocked request: ${key}`);
    return typeof hit === 'function' ? (hit as Handler)(init) : hit;
  });
}

export const calls = (method: string, url: string) =>
  mockFetch.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === method);

export const bodyOf = (call: unknown[]) => JSON.parse(((call[1] as RequestInit).body as string) ?? '{}');

/** A promise the test settles by hand, to look at a pending state. */
export function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>(r => { resolve = r; });
  return { promise, resolve };
}

export async function renderKb() {
  const out = render(<KnowledgeBaseDashboard />);
  await waitFor(() => expect(mockFetch).toHaveBeenCalled());
  return out;
}

export const waitForRow = (title: string) => screen.findByText(title);
