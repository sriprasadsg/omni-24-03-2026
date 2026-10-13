import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import raw from '../../shared/catalogue-access.json';
import {
  CATALOGUE_GROUPS,
  NAV_GROUPS,
  catalogueFor,
  findNavDrift,
  viewForHash,
  viewPermission,
} from '../../utils/catalogueAccess';
import { SIDEBAR_PRESENTATION } from '../../components/sidebarPresentation';

const ROOT = resolve(__dirname, '../..');
const read = (rel: string) => readFileSync(resolve(ROOT, rel), 'utf-8');

/** Members of an exported string-literal union in types.ts, parsed from source text. */
function unionMembers(name: string): string[] {
  const text = read('types.ts');
  const start = text.indexOf(`export type ${name}`);
  const body = text.slice(start, text.indexOf(';', start));
  return [...body.matchAll(/\|\s*'([^']+)'/g)].map(m => m[1]);
}

describe('catalogueAccess reader', () => {
  it('resolves the Mobile Device Management permission from the shared manifest', () => {
    const entry = raw.catalogues.find(c => c.view === 'mobileDeviceManagement');
    expect(viewPermission('mobileDeviceManagement')).toBe('view:mdm');
    expect(viewPermission('mobileDeviceManagement')).toBe(entry?.permission);
    expect(catalogueFor('mobileDeviceManagement')?.routes).toEqual(['/api/mdm']);
  });

  it('enforces the infra group', () => {
    expect(CATALOGUE_GROUPS.find(g => g.id === 'infra')?.enforce).toBe(true);
  });
});

describe('NAV_GROUPS', () => {
  it('has the eight sidebar groups in manifest order', () => {
    expect(NAV_GROUPS.map(g => g.id)).toEqual(raw.groups.map(g => g.id));
    expect(NAV_GROUPS.map(g => g.title)).toEqual(raw.groups.map(g => g.title));
    expect(NAV_GROUPS).toHaveLength(8);
  });

  it('holds only nav:true items, in manifest array order', () => {
    const expected = raw.catalogues.filter(c => c.nav).map(c => c.view);
    expect(NAV_GROUPS.flatMap(g => g.items.map(i => i.view))).toEqual(expected);
    expect(expected).toHaveLength(188);
  });

  it('keeps the label and permission of each manifest entry', () => {
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        const entry = raw.catalogues.find(c => c.view === item.view)!;
        expect(item.label).toBe(entry.label);
        expect(item.permission).toBe(entry.permission);
        expect(entry.group).toBe(group.id);
      }
    }
  });
});

describe('single permission per view (D-11)', () => {
  const nine: Record<string, string> = {
    agentCapabilities: 'view:agent_capabilities',
    jobs: 'view:jobs',
    llmops: 'view:llmops',
    persistenceDetection: 'view:persistence',
    sustainability: 'view:sustainability',
    swarm: 'view:swarm',
    unifiedOps: 'view:unified_ops',
    vulnerabilityManagement: 'view:vulnerabilities',
    zeroTrustQuantum: 'view:zero_trust',
  };

  it.each(Object.entries(nine))('%s resolves to the sidebar string %s', (view, permission) => {
    expect(viewPermission(view as never)).toBe(permission);
    const navItem = NAV_GROUPS.flatMap(g => g.items).find(i => i.view === view);
    expect(navItem?.permission).toBe(permission);
  });

  it('lists exactly one manifest entry per view', () => {
    const views = raw.catalogues.map(c => c.view);
    expect(new Set(views).size).toBe(views.length);
  });
});

describe('manifest membership in the type unions', () => {
  it('every manifest view is an AppView member and every AppView member has an entry', () => {
    const appViews = unionMembers('AppView');
    const manifestViews = raw.catalogues.map(c => c.view);
    expect(manifestViews.filter(v => !appViews.includes(v))).toEqual([]);
    expect(appViews.filter(v => !manifestViews.includes(v))).toEqual([]);
  });

  it('every manifest permission string is a Permission member', () => {
    const permissions = unionMembers('Permission');
    const used = new Set(raw.catalogues.map(c => c.permission));
    expect([...used].filter(p => !permissions.includes(p))).toEqual([]);
  });

  it('read and write lists are strings the backend guard evaluates (not typed as Permission)', () => {
    const permissions = unionMembers('Permission');
    const backendOnly = new Set<string>();
    for (const c of raw.catalogues) {
      [...(c.read ?? []), ...(c.write ?? [])].forEach(p => {
        expect(p).toMatch(/^[a-z_]+:[a-z_0-9]+$/);
        if (!permissions.includes(p)) backendOnly.add(p);
      });
    }
    // Known gap for 76-11: these appear only in read/write lists, never as a view permission.
    expect([...backendOnly].sort()).toEqual([
      'manage:approvals', 'manage:assets', 'manage:compliance', 'manage:procurement',
      'manage:secrets', 'manage:users', 'request:assets', 'view:secrets',
    ]);
  });
});

describe('viewForHash', () => {
  it('matches a view case-insensitively over all manifest views', () => {
    expect(viewForHash('mobiledevicemanagement')).toBe('mobileDeviceManagement');
    expect(viewForHash('MobileDeviceManagement')).toBe('mobileDeviceManagement');
    expect(viewForHash('swarm')).toBe('swarm');
  });

  it('returns undefined for an unknown hash', () => {
    expect(viewForHash('no-such-view')).toBeUndefined();
    expect(viewForHash('')).toBeUndefined();
  });
});

describe('findNavDrift (D-06)', () => {
  it('names a nav view that has no presentation entry', () => {
    expect(findNavDrift(['a', 'b'], ['a'])).toEqual({ missingPresentation: ['b'], missingManifest: [] });
  });

  it('names a presentation entry that has no manifest nav entry', () => {
    expect(findNavDrift(['a'], ['a', 'c'])).toEqual({ missingPresentation: [], missingManifest: ['c'] });
  });

  it('reports two empty lists for equal inputs, regardless of order', () => {
    expect(findNavDrift(['a', 'b'], ['b', 'a'])).toEqual({ missingPresentation: [], missingManifest: [] });
  });
});

describe('sidebar presentation vs manifest (D-06)', () => {
  it('manifest nav views and presentation keys have no drift', () => {
    const navViews = raw.catalogues.filter(c => c.nav).map(c => c.view);
    expect(findNavDrift(navViews, Object.keys(SIDEBAR_PRESENTATION))).toEqual({
      missingPresentation: [],
      missingManifest: [],
    });
  });

  it('Sidebar.tsx reads the manifest and carries no item-level permission literal', () => {
    const text = read('components/Sidebar.tsx');
    expect(text).toContain("from '../utils/catalogueAccess'");
    expect(text).not.toMatch(/permission: '(view|manage|investigate|export|request):/);
    expect(text.split('\n').length).toBeLessThan(500);
  });
});

describe('App.tsx lookups (ACC-03)', () => {
  it('resolves view permissions and hash routes from the manifest reader', () => {
    const text = read('App.tsx');
    expect(text).toContain("from './utils/catalogueAccess'");
    expect(text).toMatch(/viewPermission\(/);
    expect(text).toMatch(/viewForHash\(/);
    expect(text).not.toMatch(/Record<AppView,\s*Permission>/);
    expect(text).not.toContain('viewPermissionMap');
  });
});
