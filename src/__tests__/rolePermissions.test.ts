/**
 * Phase 77 / ACC-08, D-02, D-11: pure helpers behind the custom role editor.
 */
import { describe, it, expect } from 'vitest';
import { groupPermissions, impliedBy, effectiveSelection, lockedPermissions, builtInNameCollision } from '../../utils/rolePermissions';

describe('groupPermissions', () => {
  it('groups by manifest group order, sorts inside a group and puts unknowns in Other', () => {
    const groups = groupPermissions(['x:unknown', 'view:security', 'view:assets']);
    expect(groups.map(g => g.title)).toEqual(['Infrastructure & Assets', 'Security (SecOps)', 'Other']);
    expect(groups[0].permissions).toEqual(['view:assets']);
    expect(groups[1].permissions).toEqual(['view:security']);
    expect(groups[2].permissions).toEqual(['x:unknown']);
  });

  it('sorts permissions inside a group and omits empty groups', () => {
    const groups = groupPermissions(['view:security', 'view:assets', 'manage:assets']);
    expect(groups.find(g => g.title === 'Infrastructure & Assets')!.permissions).toEqual(['manage:assets', 'view:assets']);
    expect(groups.some(g => g.title === 'Other')).toBe(false);
  });
});

describe('impliedBy', () => {
  it('maps manage:X to view:X and request:X, nothing else', () => {
    expect(impliedBy('manage:assets')).toEqual(['view:assets', 'request:assets']);
    expect(impliedBy('view:assets')).toEqual([]);
    expect(impliedBy('request:assets')).toEqual([]);
  });
});

describe('effectiveSelection', () => {
  it('adds listed implied rows only', () => {
    const eff = effectiveSelection(new Set(['manage:assets']), ['manage:assets', 'view:assets']);
    expect([...eff].sort()).toEqual(['manage:assets', 'view:assets']);
  });

  it('releases implied rows when manage is removed, keeping manual ones', () => {
    const avail = ['manage:assets', 'view:assets'];
    expect([...effectiveSelection(new Set(['view:assets']), avail)]).toEqual(['view:assets']);
    expect([...effectiveSelection(new Set(), avail)]).toEqual([]);
  });
});

describe('lockedPermissions', () => {
  it('returns role permissions the editor cannot grant', () => {
    expect(lockedPermissions(['view:security', 'view:agents'], ['view:agents'])).toEqual(['view:security']);
  });
});

describe('builtInNameCollision', () => {
  const roles = [
    { id: 'r1', name: 'viewer', builtIn: true },
    { id: 'r2', name: 'Tenant Admin', builtIn: true },
    { id: 'r3', name: 'Helpdesk', builtIn: false },
  ] as any[];
  it('matches after normalization and returns the built-in name', () => {
    expect(builtInNameCollision('Viewer', roles)).toBe('viewer');
    expect(builtInNameCollision('Tenant-Admin', roles)).toBe('Tenant Admin');
  });
  it('ignores custom roles and unrelated names', () => {
    expect(builtInNameCollision('Helpdesk', roles)).toBeNull();
    expect(builtInNameCollision('Brand New', roles)).toBeNull();
  });
});
