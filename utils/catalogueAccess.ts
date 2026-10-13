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
