/**
 * Phase 65 (plan 65-01) CustomFieldsManager behavior:
 *  1. On mount, calls fetchAssetModelFields with the model id.
 *  2. Renders field keys grouped under their fieldset name.
 *  3. Adding a field and saving calls updateAssetModelFieldsets with the expected array.
 *  4. A rejected save renders the server's message on screen without clearing the draft.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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
    await waitFor(() => expect(screen.getByDisplayValue('ramGb')).toBeInTheDocument());
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

  it('adding a field then clicking Save calls updateAssetModelFieldsets with the expected fieldset array', async () => {
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
    updateAssetModelFieldsets.mockResolvedValue({ id: 'model-1', tenantId: 't1', name: 'ThinkPad X1' });

    render(<CustomFieldsManager modelId="model-1" modelName="ThinkPad X1" onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Hardware')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Add field to Hardware'));
    fireEvent.change(screen.getByLabelText('Key for field 0-1'), { target: { value: 'warranty_ref' } });
    fireEvent.change(screen.getByLabelText('Label for field 0-1'), { target: { value: 'Warranty Ref' } });

    fireEvent.click(screen.getByText('Save custom fields'));

    await waitFor(() => expect(updateAssetModelFieldsets).toHaveBeenCalledWith('model-1', [
      {
        name: 'Hardware',
        fields: [
          { key: 'ramGb', label: 'RAM (GB)', type: 'number', required: false, options: undefined },
          { key: 'warranty_ref', label: 'Warranty Ref', type: 'text', required: false, options: undefined },
        ],
      },
    ]));
  });

  it('a rejected save renders the server message and keeps the draft intact', async () => {
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
    updateAssetModelFieldsets.mockRejectedValue(new Error("Field key 'ramGb' is duplicated across fieldsets on this model."));

    render(<CustomFieldsManager modelId="model-1" modelName="ThinkPad X1" onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Hardware')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Save custom fields'));

    await waitFor(() =>
      expect(screen.getByText("Field key 'ramGb' is duplicated across fieldsets on this model.")).toBeInTheDocument()
    );
    // Draft is preserved — the existing field row is still on screen.
    expect(screen.getByLabelText('Key for field 0-0')).toHaveValue('ramGb');
  });

  it('removing an in-use field surfaces a warning naming the key and its asset count', async () => {
    fetchAssetModelFields.mockResolvedValue({
      modelId: 'model-1',
      modelName: 'ThinkPad X1',
      fieldsets: [
        { name: 'Hardware', fields: [{ key: 'ramGb', label: 'RAM (GB)', type: 'number' }] },
      ],
      fields: [
        { fieldsetName: 'Hardware', key: 'ramGb', label: 'RAM (GB)', type: 'number', required: false, options: [] },
      ],
      usageCounts: { ramGb: 3 },
    });

    render(<CustomFieldsManager modelId="model-1" modelName="ThinkPad X1" onClose={() => {}} />);

    await waitFor(() => expect(screen.getByText('Hardware')).toBeInTheDocument());
    expect(screen.getByText('in use by 3 assets')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Remove field 0-0'));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("'ramGb'"));
    expect(screen.getByRole('alert')).toHaveTextContent('in use by 3 assets');
  });
});
