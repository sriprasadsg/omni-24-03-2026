import type { AppView, Permission } from '../types';
import manifest from '../shared/catalogue-access.json';

/**
 * Typed reader of shared/catalogue-access.json (Phase 76). The backend guard and
 * this file resolve each catalogue's permission from the same JSON, so the
 * sidebar and the server cannot drift apart.
 */
export interface CatalogueEntry {
  view: AppView;
  label: string;
  group: string;
  nav: boolean;
  permission: Permission;
  read?: Permission[];
  write?: Permission[];
  routes: string[];
  noBackendReason?: string;
}

export interface CatalogueGroup {
  id: string;
  title: string;
  enforce: boolean;
}

export const CATALOGUE_GROUPS: CatalogueGroup[] = manifest.groups;

export const CATALOGUES: CatalogueEntry[] = manifest.catalogues as CatalogueEntry[];

export function catalogueFor(view: AppView): CatalogueEntry | undefined {
  return CATALOGUES.find(entry => entry.view === view);
}

/** The single permission the sidebar and the default read rule use for a catalogue. */
export function viewPermission(view: AppView): Permission | undefined {
  return catalogueFor(view)?.permission;
}

export interface NavItemEntry {
  view: AppView;
  label: string;
  permission: Permission;
}

export interface NavGroupEntry {
  id: string;
  title: string;
  items: ReadonlyArray<NavItemEntry>;
}

/**
 * Sidebar groups and items straight from the manifest: nav:true catalogues only,
 * in manifest array order (no sorting, so equal-looking items never reorder).
 */
export const NAV_GROUPS: ReadonlyArray<NavGroupEntry> = CATALOGUE_GROUPS.map(group => ({
  id: group.id,
  title: group.title,
  items: CATALOGUES.filter(entry => entry.group === group.id && entry.nav).map(entry => ({
    view: entry.view,
    label: entry.label,
    permission: entry.permission,
  })),
}));

/** Case-insensitive URL-hash lookup over every manifest view. */
export function viewForHash(hash: string): AppView | undefined {
  if (!hash) return undefined;
  const wanted = hash.toLowerCase();
  return CATALOGUES.find(entry => entry.view.toLowerCase() === wanted)?.view;
}

/** D-06 drift check: nav views vs presentation keys, each direction named. */
export function findNavDrift(
  navViews: readonly string[],
  presentationViews: readonly string[],
): { missingPresentation: string[]; missingManifest: string[] } {
  const presentation = new Set(presentationViews);
  const nav = new Set(navViews);
  return {
    missingPresentation: navViews.filter(view => !presentation.has(view)),
    missingManifest: presentationViews.filter(view => !nav.has(view)),
  };
}
