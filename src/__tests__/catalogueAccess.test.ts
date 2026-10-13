import { describe, it, expect } from 'vitest';
import raw from '../../shared/catalogue-access.json';
import { CATALOGUE_GROUPS, catalogueFor, viewPermission } from '../../utils/catalogueAccess';

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
