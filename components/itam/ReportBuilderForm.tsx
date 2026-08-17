import React, { useEffect, useMemo, useState } from 'react';
import {
  fetchItamReportFields,
  ItamReportField,
  ItamReportFilterCondition,
  ItamCustomReportDefinition,
} from '../../services/apiService';
import { showToast } from '../../utils/toast';
import { FilterIcon, PlusIcon, TrashIcon, SaveIcon } from '../icons';

const OPERATORS_BY_TYPE: Record<string, { value: ItamReportFilterCondition['operator']; label: string }[]> = {
  text: [
    { value: 'equals', label: 'Equals' },
    { value: 'contains', label: 'Contains' },
  ],
  date: [
    { value: 'before', label: 'Before' },
    { value: 'after', label: 'After' },
    { value: 'between', label: 'Between' },
  ],
  number: [
    { value: 'gt', label: 'Greater than' },
    { value: 'lt', label: 'Less than' },
    { value: 'between', label: 'Between' },
  ],
  enum: [{ value: 'equals', label: 'Equals' }],
};

const OPERATOR_LABELS: Record<string, string> = {
  equals: 'equals', contains: 'contains', before: 'before', after: 'after',
  between: 'between', gt: 'greater than', lt: 'less than',
};

const ENTITY_LABELS: Record<string, string> = {
  asset: 'Asset', finance: 'Finance', license: 'License', component: 'Component', consumable: 'Consumable',
};

const RUN_ERROR = "Couldn't run report. Try adjusting your filters or contact an administrator.";
const SAVE_ERROR = "Couldn't save report. Give it a name and try again.";

const inputClass = 'bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white';

interface ReportBuilderFormProps {
  onPreview: (definition: ItamCustomReportDefinition, page: number) => Promise<void>;
  onSave: (definition: ItamCustomReportDefinition) => Promise<void>;
  busy: boolean;
}

export function ReportBuilderForm({ onPreview, onSave, busy }: ReportBuilderFormProps) {
  const [fields, setFields] = useState<ItamReportField[]>([]);
  const [reportName, setReportName] = useState('');
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<ItamReportFilterCondition[]>([]);

  const [draftField, setDraftField] = useState('');
  const [draftOperator, setDraftOperator] = useState<ItamReportFilterCondition['operator'] | ''>('');
  const [draftValue, setDraftValue] = useState('');
  const [draftValue2, setDraftValue2] = useState('');

  useEffect(() => {
    fetchItamReportFields().then(setFields).catch(() => setFields([]));
  }, []);

  const fieldsByKey = useMemo(() => {
    const map: Record<string, ItamReportField> = {};
    fields.forEach((f) => { map[f.key] = f; });
    return map;
  }, [fields]);

  const fieldsByEntity = useMemo(() => {
    const map: Record<string, ItamReportField[]> = {};
    fields.forEach((f) => {
      if (!map[f.entity]) map[f.entity] = [];
      map[f.entity].push(f);
    });
    return map;
  }, [fields]);

  const draftFieldMeta = draftField ? fieldsByKey[draftField] : undefined;
  const operatorOptions = draftFieldMeta ? OPERATORS_BY_TYPE[draftFieldMeta.type] || [] : [];

  function toggleColumn(key: string) {
    setSelectedColumns((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  function handleFieldChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const key = e.target.value;
    setDraftField(key);
    const meta = fieldsByKey[key];
    const ops = meta ? OPERATORS_BY_TYPE[meta.type] || [] : [];
    setDraftOperator(ops[0]?.value || '');
    setDraftValue('');
    setDraftValue2('');
  }

  function coerceValue(type: string | undefined, raw: string): unknown {
    if (type === 'number') {
      const n = Number(raw);
      return Number.isNaN(n) ? raw : n;
    }
    return raw;
  }

  const canAddFilter = Boolean(
    draftField && draftOperator && draftValue !== '' && (draftOperator !== 'between' || draftValue2 !== ''),
  );

  function handleAddFilter() {
    if (!canAddFilter || !draftFieldMeta || !draftOperator) return;
    const condition: ItamReportFilterCondition = {
      field: draftField,
      operator: draftOperator,
      value: coerceValue(draftFieldMeta.type, draftValue),
      value2: draftOperator === 'between' ? coerceValue(draftFieldMeta.type, draftValue2) : undefined,
    };
    setFilters((prev) => [...prev, condition]);
    setDraftValue('');
    setDraftValue2('');
  }

  function removeFilter(index: number) {
    setFilters((prev) => prev.filter((_, i) => i !== index));
  }

  function buildDefinition(): ItamCustomReportDefinition {
    return { name: reportName.trim() || 'Custom Report', columns: selectedColumns, filters };
  }

  async function handleRunClick() {
    try {
      await onPreview(buildDefinition(), 1);
    } catch (e: any) {
      showToast(e?.message || RUN_ERROR, 'error');
    }
  }

  async function handleSaveClick() {
    if (!reportName.trim()) {
      showToast(SAVE_ERROR, 'error');
      return;
    }
    try {
      await onSave(buildDefinition());
    } catch (e: any) {
      showToast(e?.message || SAVE_ERROR, 'error');
    }
  }

  const valueInputType = draftFieldMeta?.type === 'number' ? 'number' : draftFieldMeta?.type === 'date' ? 'date' : 'text';

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
      <div className="mb-4">
        <label className="block text-xs font-semibold text-gray-500 mb-1" htmlFor="custom-report-name">Report Name</label>
        <input
          id="custom-report-name"
          className={`w-full ${inputClass} truncate`}
          placeholder="Untitled custom report"
          value={reportName}
          title={reportName}
          onChange={(e) => setReportName(e.target.value)}
        />
      </div>

      <div className="mb-4">
        <h4 className="text-xs font-semibold text-gray-500 mb-2">Columns</h4>
        <div className="max-h-64 overflow-y-auto space-y-3 pr-1">
          {Object.entries(fieldsByEntity).map(([entity, list]) => (
            <div key={entity}>
              <h5 className="text-[11px] font-semibold text-gray-600 uppercase mb-1">{ENTITY_LABELS[entity] || entity}</h5>
              <div className="flex flex-wrap gap-1.5">
                {list.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => toggleColumn(f.key)}
                    aria-pressed={selectedColumns.includes(f.key)}
                    className={`text-xs font-semibold px-2 py-1 rounded-full border transition-colors ${
                      selectedColumns.includes(f.key)
                        ? 'bg-cyan-600 border-cyan-500 text-white'
                        : 'bg-gray-900 border-gray-700 text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mb-4">
        <h4 className="text-xs font-semibold text-gray-500 mb-2 flex items-center gap-1">
          <FilterIcon size={12} /> Filters
        </h4>

        {filters.length > 0 && (
          <div className="max-h-48 overflow-y-auto space-y-1.5 mb-2 pr-1">
            {filters.length > 1 && <p className="text-[11px] text-gray-500">All filters are combined with AND.</p>}
            {filters.map((f, idx) => {
              const meta = fieldsByKey[f.field];
              const label = meta?.label || f.field;
              const opLabel = OPERATOR_LABELS[f.operator] || f.operator;
              const valueText = f.operator === 'between' ? `${f.value} and ${f.value2}` : String(f.value ?? '');
              return (
                <div key={idx} className="flex items-center justify-between gap-2 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5">
                  <span className="text-xs text-gray-300 truncate" title={`${label} ${opLabel} ${valueText}`}>
                    <span className="font-semibold text-white">{label}</span> {opLabel} <span className="truncate">{valueText}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => removeFilter(idx)}
                    aria-label={`Remove filter ${label}`}
                    className="text-red-400 hover:text-red-300 flex-shrink-0"
                  >
                    <TrashIcon size={14} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <select value={draftField} onChange={handleFieldChange} className={inputClass} aria-label="Filter field">
            <option value="">Select field…</option>
            {Object.entries(fieldsByEntity).map(([entity, list]) => (
              <optgroup key={entity} label={ENTITY_LABELS[entity] || entity}>
                {list.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
              </optgroup>
            ))}
          </select>
          <select
            value={draftOperator}
            onChange={(e) => setDraftOperator(e.target.value as ItamReportFilterCondition['operator'])}
            disabled={!draftFieldMeta}
            className={inputClass}
            aria-label="Filter operator"
          >
            {operatorOptions.map((op) => <option key={op.value} value={op.value}>{op.label}</option>)}
          </select>
          <input
            type={valueInputType}
            value={draftValue}
            onChange={(e) => setDraftValue(e.target.value)}
            disabled={!draftFieldMeta}
            className={inputClass}
            aria-label="Filter value"
            placeholder="Value"
          />
          {draftOperator === 'between' && (
            <input
              type={valueInputType}
              value={draftValue2}
              onChange={(e) => setDraftValue2(e.target.value)}
              className={inputClass}
              aria-label="Filter value 2"
              placeholder="Second value"
            />
          )}
          <button
            type="button"
            onClick={handleAddFilter}
            disabled={!canAddFilter}
            aria-label="Add filter"
            className="bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-white p-1.5 rounded-lg transition-colors"
          >
            <PlusIcon size={14} />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleRunClick}
          disabled={busy || selectedColumns.length === 0}
          className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
        >
          Run
        </button>
        <button
          type="button"
          onClick={handleSaveClick}
          disabled={busy || selectedColumns.length === 0 || !reportName.trim()}
          className="flex items-center gap-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
        >
          <SaveIcon size={14} /> Save Report
        </button>
        {busy && <p className="text-gray-400 text-sm">Loading…</p>}
      </div>
    </div>
  );
}
