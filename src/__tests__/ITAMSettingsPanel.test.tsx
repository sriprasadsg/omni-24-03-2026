/**
 * Phase 65 (plan 65-04) SettingsPanel behavior — ITAM-SET-01/02/03.
 * Task 1:
 *  1. The panel loads and displays stored branding values.
 *  2. Save calls saveItamSettings with the edited values.
 *  3. A rejected save renders the server's problem message.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

const getItamSettings = vi.fn();
const saveItamSettings = vi.fn();

vi.mock('../../services/apiService', () => ({
  getItamSettings: (...args: unknown[]) => getItamSettings(...args),
  saveItamSettings: (...args: unknown[]) => saveItamSettings(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { SettingsPanel } from '../../components/itam/SettingsPanel';

const STORED_SETTINGS = {
  branding: { companyName: 'Acme Corp', logoUrl: 'https://example.com/logo.png', primaryColor: '#ff00aa' },
  locale: 'en' as const,
};

describe('SettingsPanel', () => {
  beforeEach(() => {
    getItamSettings.mockReset();
    saveItamSettings.mockReset();
    getItamSettings.mockResolvedValue(STORED_SETTINGS);
  });

  it('loads and displays stored branding values', async () => {
    render(<SettingsPanel />);
    await waitFor(() => expect(screen.getByLabelText('Company name')).toHaveValue('Acme Corp'));
    expect(screen.getByLabelText('Logo URL')).toHaveValue('https://example.com/logo.png');
    expect(screen.getByLabelText('Primary colour hex value')).toHaveValue('#ff00aa');
  });

  it('Save calls saveItamSettings with the edited values', async () => {
    saveItamSettings.mockResolvedValue({ ...STORED_SETTINGS, branding: { ...STORED_SETTINGS.branding, companyName: 'New Name' } });
    render(<SettingsPanel />);
    await waitFor(() => expect(screen.getByLabelText('Company name')).toHaveValue('Acme Corp'));

    fireEvent.change(screen.getByLabelText('Company name'), { target: { value: 'New Name' } });
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(saveItamSettings).toHaveBeenCalledWith(
      expect.objectContaining({ branding: expect.objectContaining({ companyName: 'New Name' }) })
    ));
  });

  it('a rejected save renders the server problem message', async () => {
    saveItamSettings.mockRejectedValue(new Error('primaryColor must be a six-digit hex color (e.g. #0891b2).'));
    render(<SettingsPanel />);
    await waitFor(() => expect(screen.getByLabelText('Company name')).toHaveValue('Acme Corp'));

    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(
      'primaryColor must be a six-digit hex color (e.g. #0891b2).'
    ));
  });
});
