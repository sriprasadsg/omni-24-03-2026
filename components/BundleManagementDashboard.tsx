/**
 * BundleManagementDashboard
 * Admin UI for browsing feature bundles and assigning them to tenants.
 * Only accessible to Super Admin (manage:tenants permission).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { FeatureBundle, PlatformFeature, Tenant, TenantFeatures } from '../types';
import { useFeatures } from '../contexts/FeaturesContext';
import { API_BASE, authFetch } from '../services/apiService';

// ── Tiny helpers ─────────────────────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
    core:         'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    observability:'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    security:     'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    compliance:   'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    patching:     'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    devsecops:    'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
    operations:   'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
    ai_ml:        'bg-pink-100 text-pink-700 dark:bg-pink-900/40 dark:text-pink-300',
    enterprise:   'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
};

const Badge: React.FC<{ label: string; color: string }> = ({ label, color }) => (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${CATEGORY_COLORS[color] || CATEGORY_COLORS.core}`}>
        {label}
    </span>
);

// ── Feature chip inside a bundle card ────────────────────────────────────────
const FeatureChip: React.FC<{ feature: PlatformFeature }> = ({ feature }) => (
    <span
        title={feature.description}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${CATEGORY_COLORS[feature.category] || CATEGORY_COLORS.core} border-current/20`}
    >
        {feature.name}
    </span>
);

// ── Bundle card ───────────────────────────────────────────────────────────────
const BundleCard: React.FC<{
    bundle: FeatureBundle;
    selected: boolean;
    onToggle: () => void;
}> = ({ bundle, selected, onToggle }) => (
    <div
        onClick={onToggle}
        className={`relative cursor-pointer rounded-2xl border-2 p-5 transition-all duration-200 select-none
            ${selected
                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20 shadow-lg shadow-indigo-500/10'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-indigo-300 dark:hover:border-indigo-600'
            }`}
    >
        {selected && (
            <span className="absolute top-3 right-3 flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500 text-white text-xs">✓</span>
        )}
        <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl font-bold text-white shadow-md" style={{ backgroundColor: bundle.color }}>
                {bundle.name.charAt(0)}
            </div>
            <div>
                <h3 className="font-bold text-gray-900 dark:text-white text-sm">{bundle.name}</h3>
                <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{bundle.price_hint} · {bundle.feature_count} features</span>
            </div>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 leading-relaxed">{bundle.description}</p>
        <div className="flex flex-wrap gap-1">
            {bundle.features.slice(0, 6).map(f => <FeatureChip key={f.key} feature={f} />)}
            {bundle.features.length > 6 && (
                <span className="text-[11px] text-gray-400 font-medium self-center">+{bundle.features.length - 6} more</span>
            )}
        </div>
    </div>
);

// ── Main dashboard ────────────────────────────────────────────────────────────
const BundleManagementDashboard: React.FC = () => {
    const { refresh: refreshFeatures } = useFeatures();

    const [bundles, setBundles] = useState<FeatureBundle[]>([]);
    const [tenants, setTenants] = useState<Tenant[]>([]);
    const [selectedTenantId, setSelectedTenantId] = useState<string>('');
    const [tenantFeatures, setTenantFeatures] = useState<TenantFeatures | null>(null);
    const [selectedBundles, setSelectedBundles] = useState<Set<string>>(new Set());
    const [customFeatures, setCustomFeatures] = useState<string>('');
    const [saving, setSaving] = useState(false);
    const [saveMsg, setSaveMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'bundles' | 'catalog'>('bundles');
    const [catalogSearch, setCatalogSearch] = useState('');
    const [catalogData, setCatalogData] = useState<Record<string, PlatformFeature[]>>({});

    // Load bundles and tenants
    useEffect(() => {
        const load = async () => {
            setLoading(true);
            try {
                const [bRes, tRes] = await Promise.all([
                    authFetch(`${API_BASE}/bundles`),
                    authFetch(`${API_BASE}/tenants`),
                ]);
                if (bRes.ok) {
                    const d = await bRes.json();
                    setBundles(d.bundles || []);
                }
                if (tRes.ok) {
                    const d = await tRes.json();
                    setTenants((d.tenants || d || []).filter((t: Tenant) => t.id !== 'platform-admin'));
                }
            } catch { /* non-fatal */ }
            setLoading(false);
        };
        load();
    }, []);

    // Load catalog
    useEffect(() => {
        if (activeTab !== 'catalog') return;
        authFetch(`${API_BASE}/bundles/catalog`)
            .then(r => r.ok ? r.json() : null)
            .then(d => d && setCatalogData(d.catalog || {}))
            .catch(() => {});
    }, [activeTab]);

    // Load tenant's current features when tenant changes
    const loadTenantFeatures = useCallback(async (tid: string) => {
        if (!tid) return;
        try {
            const res = await authFetch(`${API_BASE}/bundles/tenant/${tid}/features`);
            if (res.ok) {
                const data: TenantFeatures = await res.json();
                setTenantFeatures(data);
                setSelectedBundles(new Set(data.assigned_bundles));
                setCustomFeatures((data.custom_features || []).join(', '));
            } else {
                setTenantFeatures(null);
                setSelectedBundles(new Set());
                setCustomFeatures('');
            }
        } catch {
            setTenantFeatures(null);
        }
    }, []);

    useEffect(() => {
        if (selectedTenantId) loadTenantFeatures(selectedTenantId);
    }, [selectedTenantId, loadTenantFeatures]);

    const toggleBundle = (key: string) => {
        setSelectedBundles(prev => {
            const next = new Set(prev);
            next.has(key) ? next.delete(key) : next.add(key);
            return next;
        });
    };

    const handleSave = async () => {
        if (!selectedTenantId) return;
        setSaving(true);
        setSaveMsg(null);
        try {
            const custom = customFeatures
                .split(',')
                .map(s => s.trim())
                .filter(Boolean);
            const res = await authFetch(`${API_BASE}/bundles/tenant/${selectedTenantId}/assign`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    assigned_bundles: Array.from(selectedBundles),
                    custom_features: custom,
                    blocked_features: [],
                }),
            });
            if (res.ok) {
                const data = await res.json();
                setSaveMsg({ type: 'ok', text: `Saved — ${data.effective_feature_count} features now active.` });
                refreshFeatures();
                loadTenantFeatures(selectedTenantId);
            } else {
                const err = await res.json().catch(() => ({}));
                setSaveMsg({ type: 'err', text: err.detail || 'Save failed.' });
            }
        } catch {
            setSaveMsg({ type: 'err', text: 'Network error.' });
        }
        setSaving(false);
    };

    const allFeatureKeys = Array.from(
        new Set(bundles.flatMap(b => b.features.map(f => f.key)))
    );
    const previewFeatureCount = new Set(
        bundles
            .filter(b => selectedBundles.has(b.key))
            .flatMap(b => b.features.map(f => f.key))
    ).size;

    // ── Catalog tab filter ───────────────────────────────────────────────────
    const filteredCatalog = Object.entries(catalogData).reduce<Record<string, PlatformFeature[]>>(
        (acc, [cat, features]) => {
            const q = catalogSearch.toLowerCase();
            const filtered = features.filter(
                f => !q || f.name.toLowerCase().includes(q) || f.description.toLowerCase().includes(q)
            );
            if (filtered.length) acc[cat] = filtered;
            return acc;
        },
        {}
    );

    if (loading) return (
        <div className="flex items-center justify-center h-64 text-gray-400">
            Loading bundles…
        </div>
    );

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Feature Bundle Management</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        Assign feature bundles to customers — mix and match to build the exact plan they need.
                    </p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => setActiveTab('bundles')}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'bundles' ? 'bg-indigo-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:border-indigo-400'}`}
                    >
                        Assign Bundles
                    </button>
                    <button
                        onClick={() => setActiveTab('catalog')}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'catalog' ? 'bg-indigo-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:border-indigo-400'}`}
                    >
                        Feature Catalog
                    </button>
                </div>
            </div>

            {activeTab === 'catalog' ? (
                /* ── Catalog Tab ──────────────────────────────────────────── */
                <div className="space-y-4">
                    <input
                        value={catalogSearch}
                        onChange={e => setCatalogSearch(e.target.value)}
                        placeholder="Search features…"
                        className="w-full max-w-md px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    {Object.entries(filteredCatalog).map(([cat, features]) => (
                        <div key={cat} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
                            <div className="flex items-center gap-2 mb-4">
                                <Badge label={cat.replace('_', ' ')} color={cat} />
                                <span className="text-xs text-gray-400">{features.length} features</span>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {features.map(f => (
                                    <div key={f.key} className="p-3 rounded-xl bg-gray-50 dark:bg-gray-700/50 border border-gray-100 dark:border-gray-700">
                                        <div className="flex items-start justify-between gap-2">
                                            <span className="font-medium text-sm text-gray-900 dark:text-white">{f.name}</span>
                                            <Badge label={f.minTier} color="core" />
                                        </div>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">{f.description}</p>
                                        <code className="text-[10px] text-indigo-500 dark:text-indigo-400 mt-1 block font-mono">{f.key}</code>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                /* ── Assign Tab ───────────────────────────────────────────── */
                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

                    {/* Left — tenant selector + bundle picker */}
                    <div className="xl:col-span-2 space-y-5">

                        {/* Tenant selector */}
                        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
                            <h2 className="font-semibold text-gray-900 dark:text-white mb-3 text-sm uppercase tracking-wider">1 · Select Customer</h2>
                            <select
                                value={selectedTenantId}
                                onChange={e => setSelectedTenantId(e.target.value)}
                                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            >
                                <option value="">— choose a tenant —</option>
                                {tenants.map(t => (
                                    <option key={t.id} value={t.id}>
                                        {t.name} ({t.subscriptionTier})
                                    </option>
                                ))}
                            </select>
                            {tenantFeatures && (
                                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                                    Currently: <strong>{tenantFeatures.assigned_bundles.length}</strong> bundles assigned →{' '}
                                    <strong>{tenantFeatures.effective_features.length}</strong> features active
                                </p>
                            )}
                        </div>

                        {/* Bundle grid */}
                        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
                            <h2 className="font-semibold text-gray-900 dark:text-white mb-4 text-sm uppercase tracking-wider">2 · Select Bundles</h2>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                {bundles.map(b => (
                                    <BundleCard
                                        key={b.key}
                                        bundle={b}
                                        selected={selectedBundles.has(b.key)}
                                        onToggle={() => toggleBundle(b.key)}
                                    />
                                ))}
                            </div>
                        </div>

                        {/* Custom features */}
                        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
                            <h2 className="font-semibold text-gray-900 dark:text-white mb-2 text-sm uppercase tracking-wider">3 · Custom Add-ons (optional)</h2>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                                Add individual feature keys not covered by the selected bundles, separated by commas.
                            </p>
                            <input
                                value={customFeatures}
                                onChange={e => setCustomFeatures(e.target.value)}
                                placeholder="e.g. cissp_oracle, chaos_engineering"
                                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                            <p className="text-[10px] text-gray-400 mt-1.5">
                                Valid keys: {allFeatureKeys.slice(0, 10).join(', ')}…
                            </p>
                        </div>
                    </div>

                    {/* Right — summary panel */}
                    <div className="space-y-4">
                        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 sticky top-6">
                            <h2 className="font-semibold text-gray-900 dark:text-white mb-4 text-sm uppercase tracking-wider">Summary</h2>

                            {!selectedTenantId ? (
                                <p className="text-sm text-gray-400">Select a customer to get started.</p>
                            ) : (
                                <>
                                    <div className="mb-4 space-y-2">
                                        <div className="flex justify-between text-sm">
                                            <span className="text-gray-500">Customer</span>
                                            <span className="font-medium text-gray-900 dark:text-white">
                                                {tenants.find(t => t.id === selectedTenantId)?.name}
                                            </span>
                                        </div>
                                        <div className="flex justify-between text-sm">
                                            <span className="text-gray-500">Bundles</span>
                                            <span className="font-bold text-indigo-600 dark:text-indigo-400">{selectedBundles.size}</span>
                                        </div>
                                        <div className="flex justify-between text-sm">
                                            <span className="text-gray-500">Est. features</span>
                                            <span className="font-bold text-green-600 dark:text-green-400">~{previewFeatureCount}</span>
                                        </div>
                                    </div>

                                    {selectedBundles.size > 0 && (
                                        <div className="mb-4">
                                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Selected bundles</p>
                                            <div className="space-y-1.5">
                                                {bundles.filter(b => selectedBundles.has(b.key)).map(b => (
                                                    <div key={b.key} className="flex items-center gap-2 text-sm">
                                                        <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: b.color }} />
                                                        <span className="text-gray-700 dark:text-gray-300">{b.name}</span>
                                                        <span className="ml-auto text-xs text-gray-400">{b.feature_count}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {saveMsg && (
                                        <div className={`mb-3 p-3 rounded-lg text-sm ${saveMsg.type === 'ok' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'}`}>
                                            {saveMsg.text}
                                        </div>
                                    )}

                                    <button
                                        onClick={handleSave}
                                        disabled={saving}
                                        className="w-full py-2.5 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold text-sm transition-colors"
                                    >
                                        {saving ? 'Saving…' : 'Apply Bundle Assignment'}
                                    </button>

                                    {selectedBundles.size === 0 && (
                                        <p className="text-xs text-gray-400 text-center mt-2">
                                            No bundles selected — customer will use tier-based access only.
                                        </p>
                                    )}
                                </>
                            )}
                        </div>

                        {/* Currently active features */}
                        {tenantFeatures && tenantFeatures.effective_features.length > 0 && (
                            <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
                                <h2 className="font-semibold text-gray-900 dark:text-white mb-3 text-sm uppercase tracking-wider">
                                    Currently Active ({tenantFeatures.effective_features.length})
                                </h2>
                                <div className="flex flex-wrap gap-1.5 max-h-52 overflow-y-auto">
                                    {tenantFeatures.effective_features.map(f => (
                                        <FeatureChip key={f.key} feature={f} />
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default BundleManagementDashboard;
