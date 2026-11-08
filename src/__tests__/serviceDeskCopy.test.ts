/**
 * 85-02: the service desk's fixed UI copy matches the server copy.
 *
 * components/serviceDesk/serviceDeskCopy.ts and backend/service_desk/messages.py each hold the five strings the
 * requester sees everywhere (D-13, D-22, D-24, D-25). This test reads the Python file as text and asserts that
 * the five appear in it verbatim, so the portal, the tray and the server can never drift apart.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import * as copy from '../../components/serviceDesk/serviceDeskCopy';

const ROOT = resolve(__dirname, '../..');
const MESSAGES_PY = readFileSync(resolve(ROOT, 'backend/service_desk/messages.py'), 'utf-8');

/** Join Python implicit string concatenation ("..."\n    "...") so a wrapped sentence reads as one line. */
const PY_JOINED = MESSAGES_PY.replace(/"\s*\n\s*"/g, '');

function* strings(value: unknown, path: string): Generator<[string, string]> {
  if (typeof value === 'string') yield [path, value];
  else if (Array.isArray(value)) for (const [i, v] of value.entries()) yield* strings(v, `${path}[${i}]`);
  else if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) yield* strings(v, `${path}.${k}`);
  }
}

describe('shared strings', () => {
  const shared: Array<[string, string]> = [
    ['MARK', 'AI-assisted answer from your IT knowledge base'],
    ['FOOTER', "Not right? Choose 'I still need help' and a person will take over."],
    ['HANDOFF_NOTICE', 'A person from IT will look at this.'],
    ['WITHDRAWN_NOTICE', 'This answer was withdrawn; a person will follow up.'],
    ['OFFLINE_STATUS', "Offline: the local model isn't running"],
  ];

  it.each(shared)('%s is the agreed text in the UI copy', (name, text) => {
    expect((copy as unknown as Record<string, string>)[name]).toBe(text);
  });

  it.each(shared)('%s appears verbatim in backend/service_desk/messages.py', (name, text) => {
    expect(PY_JOINED).toContain(`${name} = "${text}"`);
  });

  it('the draft reason lines match the server text', () => {
    for (const [key, text] of Object.entries(copy.DRAFT_PANEL.draftReasons)) {
      expect(PY_JOINED, key).toContain(`"${text}"`);
    }
  });

  it('the requester notice title matches the server', () => {
    expect(PY_JOINED).toContain(`NOTICE_TITLE = "${copy.REQUESTER.noticeTitle}"`);
  });
});

describe('every exported string', () => {
  const exported = Object.entries(copy).filter(([, v]) => typeof v !== 'function');

  it('exports a good number of constants', () => {
    expect(exported.length).toBeGreaterThanOrEqual(20);
  });

  it('is non-empty and has no leftover whitespace at either end', () => {
    for (const [name, value] of exported) {
      for (const [path, text] of strings(value, name)) {
        expect(text.length, path).toBeGreaterThan(0);
        expect(text, path).toBe(text.trim());
      }
    }
  });

  it('keeps the three mode names exact', () => {
    expect([copy.MODES.off.title, copy.MODES.drafts.title, copy.MODES.post.title])
      .toEqual(['Off', 'Drafts only', 'Post answers']);
  });
});

describe('fill', () => {
  it('replaces named fields and leaves unknown ones in place', () => {
    expect(copy.fill('Open ticket {number}', { number: 'TKT-0042' })).toBe('Open ticket TKT-0042');
    expect(copy.fill('{n}/{max}', { n: 3 })).toBe('3/{max}');
  });

  it('fills the spec sentences', () => {
    expect(copy.fill(copy.READINESS.level.notMet, { level: 'Suggest' }))
      .toBe('Autonomous Ops is at Suggest, so answers stay drafts. Only the level screen changes this.');
    expect(copy.fill(copy.ACTIVITY.undoAria, { number: 'TKT-0042' })).toBe('Undo: Post ticket answer on TKT-0042');
  });
});
