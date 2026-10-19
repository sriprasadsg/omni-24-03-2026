import { CATALOGUES, CATALOGUE_GROUPS } from './catalogueAccess';
import { normalizeRoleName } from './permissions';
import { ApiRole, isBuiltInRole } from '../services/roleApi';

export interface PermissionGroup { id: string; title: string; permissions: string[]; }

const OTHER: PermissionGroup = { id: 'other', title: 'Other', permissions: [] };

/** The manifest group of the first catalogue entry that names the permission, else null. */
function groupIdOf(permission: string): string | null {
  const entry = CATALOGUES.find(e =>
    e.permission === permission || (e.read ?? []).includes(permission) || (e.write ?? []).includes(permission));
  return entry ? entry.group : null;
}

/** Group permissions in manifest group order (sorted inside a group); unknown ones go to 'Other'. Empty groups are omitted. */
export function groupPermissions(perms: string[]): PermissionGroup[] {
  const groups = [...CATALOGUE_GROUPS.map(g => ({ id: g.id, title: g.title, permissions: [] as string[] })), { ...OTHER, permissions: [] as string[] }];
  for (const p of perms) {
    const id = groupIdOf(p) ?? 'other';
    (groups.find(g => g.id === id) ?? groups[groups.length - 1]).permissions.push(p);
  }
  return groups.filter(g => g.permissions.length > 0).map(g => ({ ...g, permissions: [...g.permissions].sort() }));
}

/** D-11 display: manage:X also grants view:X and request:X. */
export function impliedBy(permission: string): string[] {
  if (!permission.startsWith('manage:')) return [];
  const resource = permission.slice('manage:'.length);
  return [`view:${resource}`, `request:${resource}`];
}

/** The manual selection plus everything a ticked manage: permission implies, kept only when the catalogue lists it. */
export function effectiveSelection(manual: Set<string>, available: string[]): Set<string> {
  const listed = new Set(available);
  const result = new Set(manual);
  for (const p of manual) {
    for (const implied of impliedBy(p)) if (listed.has(implied)) result.add(implied);
  }
  return result;
}

/** Permissions already on the role that the editor cannot grant (they stay and are kept on save). */
export function lockedPermissions(rolePerms: string[], grantable: string[]): string[] {
  const ok = new Set(grantable);
  return rolePerms.filter(p => !ok.has(p));
}

/** The built-in role whose normalized name matches, or null. Returns that role's own name. */
export function builtInNameCollision(name: string, roles: ApiRole[]): string | null {
  const wanted = normalizeRoleName(name);
  if (!wanted) return null;
  const hit = roles.find(r => isBuiltInRole(r) && normalizeRoleName(r.name) === wanted);
  return hit ? hit.name : null;
}
