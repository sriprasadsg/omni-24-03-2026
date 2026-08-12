/**
 * Phase 65 (plan 65-01) CustomFieldsManager behavior:
 *  1. On mount, calls fetchAssetModelFields with the model id.
 *  2. Renders field keys grouped under their fieldset name.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const fetchAssetModelFields = vi.fn();
const updateAssetModelFieldsets = vi.fn();

vi.mock('../../services/apiService', () => ({
  fetchAssetModelFields: (...args: unknown[]) => fetchAssetModelFields(...args),
  updateAssetModelFieldsets: (...args: unknown[]) => updateAssetModelFieldsets(...args),
}));

vi.mock('../../utils/toast', () => ({ showToast: vi.fn() }));

import { CustomFieldsManager } from '../../components/itam/CustomFieldsManager';

describe('CustomFieldsManager', () => {
  beforeEach(() => {
    fetchAssetModelFields.mockReset();
    updateAssetModelFieldsets.mockReset();
  });

  it('loads and displays a model\'s custom fields grouped by fieldset', async () => {
    fetchAssetModelFields.mockResolvedValue({
      modelId: 'model-1',
      modelName: 'ThinkPad X1',
      fieldsets: [
        { name: 'Hardware', fields: [{ key: 'ramGb', label: 'RAM (GB)', type: 'number' }] },
      ],
      fields: [
        { fieldsetName: 'Hardware', key: 'ramGb', label: 'RAM (GB)', type: 'number', required: false, options: [] },
      ],
      usageCounts: {},
    });

    render(<CustomFieldsManager modelId="model-1" modelName="ThinkPad X1" onClose={() => {}} />);

    await waitFor(() => expect(fetchAssetModelFields).toHaveBeenCalledWith('model-1'));
    await waitFor(() => expect(screen.getByText('ramGb')).toBeInTheDocument());
    expect(screen.getByText('Hardware')).toBeInTheDocument();
  });

  it('shows the empty state when a model has no fields', async () => {
    fetchAssetModelFields.mockResolvedValue({
      modelId: 'model-2',
      modelName: 'Empty Model',
      fieldsets: [],
      fields: [],
      usageCounts: {},
    });

    render(<CustomFieldsManager modelId="model-2" modelName="Empty Model" onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('No custom fields on this model yet.')).toBeInTheDocument());
  });
});
