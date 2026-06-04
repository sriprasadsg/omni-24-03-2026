import React, { useState, useEffect, useRef } from 'react';
import { CustomYaraRule } from '../types';
import {
    fetchCustomYaraRules, saveCustomYaraRule, deleteCustomYaraRule, validateYaraRule
} from '../services/apiService';
import { PlusCircleIcon, TrashIcon, CheckIcon, AlertTriangleIcon, CogIcon } from './icons';

const STARTER_TEMPLATE = `rule CustomRule {
    meta:
        description = "Describe what this rule detects"
        severity = "medium"
    strings:
        $s1 = "suspicious_string" nocase
    condition:
        $s1
}`;

export const YaraRuleEditor: React.FC = () => {
    const [rules, setRules] = useState<CustomYaraRule[]>([]);
    const [selected, setSelected] = useState<CustomYaraRule | null>(null);
    const [isNew, setIsNew] = useState(false);
    const [name, setName] = useState('');
    const [description, setDescription] = useState('');
    const [content, setContent] = useState('');
    const [enabled, setEnabled] = useState(true);
    const [saving, setSaving] = useState(false);
    const [validating, setValidating] = useState(false);
    const [validationResult, setValidationResult] = useState<{ valid: boolean; error?: string } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        fetchCustomYaraRules().then(setRules);
    }, []);

    const openRule = (rule: CustomYaraRule) => {
        setSelected(rule);
        setIsNew(false);
        setName(rule.name);
        setDescription(rule.description || '');
        setContent(rule.content);
        setEnabled(rule.enabled);
        setValidationResult(null);
        setError(null);
    };

    const openNew = () => {
        setSelected(null);
        setIsNew(true);
        setName('');
        setDescription('');
        setContent(STARTER_TEMPLATE);
        setEnabled(true);
        setValidationResult(null);
        setError(null);
    };

    const handleValidate = async () => {
        setValidating(true);
        setValidationResult(null);
        const result = await validateYaraRule(content);
        setValidationResult(result);
        setValidating(false);
    };

    const handleSave = async () => {
        if (!name.trim()) { setError('Rule name is required'); return; }
        setSaving(true);
        setError(null);
        try {
            const payload = { ...(selected && !isNew ? { id: selected.id } : {}), name, description, content, enabled };
            const saved = await saveCustomYaraRule(payload);
            setRules(prev => {
                const exists = prev.some(r => r.id === saved.id);
                return exists ? prev.map(r => r.id === saved.id ? saved : r) : [...prev, saved];
            });
            openRule(saved);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Save failed');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (rule: CustomYaraRule) => {
        if (!window.confirm(`Delete rule "${rule.name}"?`)) return;
        await deleteCustomYaraRule(rule.id);
        setRules(prev => prev.filter(r => r.id !== rule.id));
        if (selected?.id === rule.id) {
            setSelected(null);
            setIsNew(false);
        }
    };

    const handleTabKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key !== 'Tab') return;
        e.preventDefault();
        const el = e.currentTarget;
        const start = el.selectionStart;
        const end = el.selectionEnd;
        const newContent = content.substring(0, start) + '    ' + content.substring(end);
        setContent(newContent);
        requestAnimationFrame(() => {
            el.selectionStart = el.selectionEnd = start + 4;
        });
    };

    const hasChanges = selected
        ? name !== selected.name || description !== (selected.description || '') || content !== selected.content || enabled !== selected.enabled
        : isNew;

    return (
        <div className="flex h-full min-h-[600px] rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-md">
            {/* Rule list sidebar */}
            <div className="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 flex flex-col">
                <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                    <span className="text-sm font-semibold text-gray-800 dark:text-white">Custom Rules</span>
                    <button onClick={openNew} title="New rule" className="p-1 text-primary-600 hover:text-primary-800">
                        <PlusCircleIcon size={18} />
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto">
                    {rules.length === 0 && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 p-3">No custom rules yet. Click + to create one.</p>
                    )}
                    {rules.map(rule => (
                        <button
                            key={rule.id}
                            onClick={() => openRule(rule)}
                            className={`w-full text-left px-3 py-2.5 border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/50 flex items-center justify-between group ${selected?.id === rule.id ? 'bg-primary-50 dark:bg-primary-900/30' : ''}`}
                        >
                            <div className="min-w-0">
                                <p className={`text-xs font-medium truncate ${selected?.id === rule.id ? 'text-primary-700 dark:text-primary-300' : 'text-gray-800 dark:text-gray-200'}`}>
                                    {rule.name}
                                </p>
                                <p className={`text-xs ${rule.enabled ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                                    {rule.enabled ? 'Enabled' : 'Disabled'}
                                </p>
                            </div>
                            <button
                                onClick={e => { e.stopPropagation(); handleDelete(rule); }}
                                className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-600 flex-shrink-0"
                            >
                                <TrashIcon size={13} />
                            </button>
                        </button>
                    ))}
                </div>
            </div>

            {/* Editor panel */}
            <div className="flex-1 flex flex-col">
                {!(selected || isNew) ? (
                    <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500 text-sm">
                        Select a rule or click + to create one
                    </div>
                ) : (
                    <>
                        <div className="p-4 border-b border-gray-200 dark:border-gray-700 space-y-3">
                            <div className="flex flex-wrap gap-3">
                                <input
                                    type="text"
                                    value={name}
                                    onChange={e => setName(e.target.value)}
                                    placeholder="Rule name"
                                    className="flex-1 min-w-[160px] px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                />
                                <input
                                    type="text"
                                    value={description}
                                    onChange={e => setDescription(e.target.value)}
                                    placeholder="Description (optional)"
                                    className="flex-1 min-w-[200px] px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                />
                                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                                    <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} className="rounded" />
                                    Enabled
                                </label>
                            </div>
                        </div>

                        <div className="flex-1 p-4 flex flex-col gap-3">
                            <textarea
                                ref={textareaRef}
                                value={content}
                                onChange={e => { setContent(e.target.value); setValidationResult(null); }}
                                onKeyDown={handleTabKey}
                                spellCheck={false}
                                className="flex-1 min-h-[280px] w-full font-mono text-xs px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 resize-y focus:outline-none focus:ring-1 focus:ring-primary-500"
                                placeholder={STARTER_TEMPLATE}
                            />

                            {validationResult && (
                                <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-md ${validationResult.valid ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300' : 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'}`}>
                                    {validationResult.valid
                                        ? <><CheckIcon size={14} /> Syntax is valid</>
                                        : <><AlertTriangleIcon size={14} /> {validationResult.error}</>}
                                </div>
                            )}

                            {error && (
                                <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-md bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300">
                                    <AlertTriangleIcon size={14} /> {error}
                                </div>
                            )}

                            <div className="flex items-center gap-3">
                                <button
                                    onClick={handleValidate}
                                    disabled={validating || !content.trim()}
                                    className="flex items-center px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50"
                                >
                                    {validating ? <CogIcon size={14} className="mr-1.5 animate-spin" /> : null}
                                    Validate Syntax
                                </button>
                                <button
                                    onClick={handleSave}
                                    disabled={saving || !hasChanges}
                                    className="flex items-center px-4 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {saving ? <CogIcon size={14} className="mr-1.5 animate-spin" /> : null}
                                    {isNew ? 'Create Rule' : 'Save Changes'}
                                </button>
                                {selected && (
                                    <button
                                        onClick={() => handleDelete(selected)}
                                        className="flex items-center px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 border border-red-300 dark:border-red-700 rounded-md hover:bg-red-50 dark:hover:bg-red-900/30"
                                    >
                                        <TrashIcon size={14} className="mr-1.5" />
                                        Delete
                                    </button>
                                )}
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};
