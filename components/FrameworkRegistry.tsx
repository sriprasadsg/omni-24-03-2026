import React, { useState, useId } from 'react';
import { ComplianceFramework } from '../types';
import { ShieldCheckIcon, BotIcon, ShieldLockIcon, GavelIcon, HeartPulseIcon, CreditCardIcon, BookOpenCheckIcon, PlusIcon, ExternalLinkIcon, SearchIcon } from './icons';
import { Modal } from './Modal';
import { addComplianceFramework } from '../services/apiService';

// ── Official compliance framework catalog ──────────────────────────────────

const FRAMEWORK_CATALOG = [
  { id: 'iso27001',     shortName: 'ISO 27001',     name: 'ISO 27001:2022',                        category: 'Information Security', url: 'https://www.iso.org/standard/27001',            description: 'International standard for information security management systems.' },
  { id: 'soc2',         shortName: 'SOC 2',          name: 'SOC 2 (Type II)',                        category: 'Trust Services',       url: 'https://www.aicpa-cima.com/resources/landing/soc-2', description: 'AICPA trust-services criteria for security, availability, and confidentiality.' },
  { id: 'hipaa',        shortName: 'HIPAA',           name: 'HIPAA Security Rule',                   category: 'Healthcare',           url: 'https://www.hhs.gov/hipaa',                     description: 'US healthcare data privacy and security regulation.' },
  { id: 'pci-dss',      shortName: 'PCI-DSS',         name: 'PCI-DSS v4.0',                          category: 'Payment Security',     url: 'https://www.pcisecuritystandards.org/',         description: 'Payment Card Industry Data Security Standard.' },
  { id: 'nistcsf',      shortName: 'NIST CSF',        name: 'NIST Cybersecurity Framework 2.0',      category: 'Risk Management',      url: 'https://www.nist.gov/cyberframework',            description: 'NIST framework for improving critical infrastructure cybersecurity.' },
  { id: 'gdpr',         shortName: 'GDPR',            name: 'General Data Protection Regulation',    category: 'Privacy',              url: 'https://gdpr.eu/',                              description: 'EU regulation on data protection and privacy.' },
  { id: 'iso42001',     shortName: 'ISO 42001',       name: 'ISO/IEC 42001:2023',                    category: 'AI Governance',        url: 'https://www.iso.org/standard/81230.html',       description: 'AI management system standard.' },
  { id: 'nist_800_53',  shortName: 'NIST 800-53',     name: 'NIST SP 800-53 Rev.5',                  category: 'Federal Security',     url: 'https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final', description: 'Security controls for federal information systems.' },
  { id: 'nist_800_171', shortName: 'NIST 800-171',    name: 'NIST SP 800-171 Rev.2',                 category: 'Federal Security',     url: 'https://csrc.nist.gov/publications/detail/sp/800-171/rev-2/final', description: 'Protecting controlled unclassified information.' },
  { id: 'cmmc_l2',      shortName: 'CMMC L2',         name: 'CMMC Level 2',                          category: 'Defense',              url: 'https://dodcio.defense.gov/CMMC/',              description: 'Cybersecurity Maturity Model Certification for DoD contractors.' },
  { id: 'fedramp_moderate', shortName: 'FedRAMP',     name: 'FedRAMP Moderate',                      category: 'Federal Cloud',        url: 'https://www.fedramp.gov/',                      description: 'US government cloud security authorization program.' },
  { id: 'hitrust_csf',  shortName: 'HITRUST',         name: 'HITRUST CSF v11',                       category: 'Healthcare',           url: 'https://hitrustalliance.net/',                  description: 'Healthcare information trust alliance common security framework.' },
  { id: 'cis_v8',       shortName: 'CIS v8',          name: 'CIS Controls v8',                       category: 'Best Practices',       url: 'https://www.cisecurity.org/controls/v8',        description: 'Center for Internet Security prioritized safeguards.' },
  { id: 'cobit_2019',   shortName: 'COBIT 2019',      name: 'COBIT 2019',                            category: 'Governance',           url: 'https://www.isaca.org/resources/cobit',         description: 'ISACA framework for IT governance and management.' },
  { id: 'dora',         shortName: 'DORA',            name: 'Digital Operational Resilience Act',    category: 'EU Financial',         url: 'https://www.eiopa.europa.eu/digital-operational-resilience-act-dora_en', description: 'EU regulation on digital resilience for financial sector.' },
  { id: 'nis2',         shortName: 'NIS2',            name: 'NIS2 Directive',                        category: 'EU Cybersecurity',     url: 'https://digital-strategy.ec.europa.eu/en/policies/nis2-directive', description: 'EU network and information systems security directive.' },
  { id: 'sox_itgc',     shortName: 'SOX ITGC',        name: 'Sarbanes-Oxley ITGC',                   category: 'Financial Reporting',  url: 'https://sarbanes-oxley-101.com/',               description: 'IT general controls for SOX financial compliance.' },
  { id: 'csa_star',     shortName: 'CSA STAR',        name: 'CSA STAR Level 1',                      category: 'Cloud Security',       url: 'https://cloudsecurityalliance.org/star',        description: 'Cloud Security Alliance security, trust, assurance & risk program.' },
  { id: 'ccpa',         shortName: 'CCPA',            name: 'California Consumer Privacy Act',       category: 'Privacy',              url: 'https://oag.ca.gov/privacy/ccpa',               description: 'California data privacy rights and business obligations.' },
  { id: 'iso27701',     shortName: 'ISO 27701',       name: 'ISO/IEC 27701:2019',                    category: 'Privacy Management',   url: 'https://www.iso.org/standard/71670.html',       description: 'Privacy information management extension to ISO 27001.' },
  { id: 'iso9001_2015', shortName: 'ISO 9001',        name: 'ISO 9001:2015',                         category: 'Quality Management',   url: 'https://www.iso.org/iso-9001-quality-management.html', description: 'International standard for quality management systems.' },
  { id: 'iso31000_2018', shortName: 'ISO 31000',      name: 'ISO 31000:2018',                        category: 'Risk Management',      url: 'https://www.iso.org/iso-31000-risk-management.html', description: 'Guidelines for risk management principles and processes.' },
  { id: 'swift_csp',    shortName: 'SWIFT CSP',       name: 'SWIFT Customer Security Programme',     category: 'Financial Services',   url: 'https://www.swift.com/myswift/customer-security-programme-csp', description: 'SWIFT mandatory security controls for financial messaging.' },
  { id: 'nist_ai_rmf',  shortName: 'NIST AI RMF',    name: 'NIST AI Risk Management Framework',     category: 'AI Governance',        url: 'https://www.nist.gov/system/files/documents/2023/01/26/AI-RMF-First-Draft.pdf', description: 'NIST framework for managing AI risks across the lifecycle.' },
  { id: 'soc1_type1',   shortName: 'SOC 1 T1',        name: 'SOC 1 Type I',                          category: 'Financial Controls',   url: 'https://www.aicpa-cima.com/resources/landing/soc-1', description: 'Report on management description and controls suitability.' },
];

const CATEGORIES = ['All', ...Array.from(new Set(FRAMEWORK_CATALOG.map(f => f.category))).sort()];

// ── Modal ──────────────────────────────────────────────────────────────────

const fieldCls = 'h-9 px-3 text-sm rounded-xl text-gray-900 dark:text-white bg-white dark:bg-white/[0.04] border border-gray-200 dark:border-white/10 placeholder:text-gray-400 focus:outline-none focus:border-primary-500';
const labelCls = 'block text-[13px] font-medium text-gray-700 dark:text-gray-300 mb-1';

const AddComplianceModal: React.FC<{
    existingIds: string[];
    onClose: () => void;
    onAdded: (f: ComplianceFramework) => void;
}> = ({ existingIds, onClose, onAdded }) => {
    const [tab, setTab]             = useState<'catalog' | 'custom'>('catalog');
    const [catFilter, setCatFilter] = useState('All');
    const [search, setSearch]       = useState('');
    const [adding, setAdding]       = useState<string | null>(null);
    const [err, setErr]             = useState('');
    const fieldId = useId();

    // Custom form state
    const [custom, setCustom] = useState({ name: '', shortName: '', description: '', category: '', official_url: '' });

    const filtered = FRAMEWORK_CATALOG.filter(f => {
        const notAdded = !existingIds.includes(f.id);
        const catMatch = catFilter === 'All' || f.category === catFilter;
        const q = search.toLowerCase();
        const textMatch = !q || f.name.toLowerCase().includes(q) || f.shortName.toLowerCase().includes(q) || f.category.toLowerCase().includes(q);
        return notAdded && catMatch && textMatch;
    });

    const handleAddCatalog = async (f: typeof FRAMEWORK_CATALOG[0]) => {
        setAdding(f.id); setErr('');
        try {
            const created = await addComplianceFramework({ id: f.id, name: f.name, shortName: f.shortName, description: f.description, category: f.category, official_url: f.url });
            onAdded(created);
            onClose();
        } catch (e: any) { setErr(e.message ?? 'Failed to add framework'); }
        finally { setAdding(null); }
    };

    const handleAddCustom = async () => {
        if (!custom.name.trim()) { setErr('Framework name is required'); return; }
        setAdding('custom'); setErr('');
        try {
            const created = await addComplianceFramework(custom);
            onAdded(created);
            onClose();
        } catch (e: any) { setErr(e.message ?? 'Failed to create framework'); }
        finally { setAdding(null); }
    };

    const footer = tab === 'custom' ? (
        <>
            <button onClick={onClose} className="h-9 px-4 text-sm font-medium text-gray-700 dark:text-gray-200 glass rounded-xl">Cancel</button>
            <button onClick={handleAddCustom} disabled={adding === 'custom'}
                className="inline-flex items-center gap-1.5 h-9 px-4 text-sm font-semibold text-white rounded-xl bg-primary-600 hover:bg-primary-700 disabled:opacity-50">
                <PlusIcon size={14} />
                {adding === 'custom' ? 'Creating…' : 'Create framework'}
            </button>
        </>
    ) : undefined;

    return (
        <Modal isOpen onClose={onClose} title="Add a compliance framework" size="2xl" footer={footer}
            icon={<ShieldCheckIcon size={20} className="text-primary-500" />}>
            <div className="space-y-4">
                <div role="group" aria-label="Framework source" className="inline-flex p-0.5 rounded-xl bg-gray-100 dark:bg-white/[0.05] ring-1 ring-inset ring-gray-200/70 dark:ring-white/[0.06]">
                    {(['catalog', 'custom'] as const).map(t => (
                        <button key={t} onClick={() => { setTab(t); setErr(''); }} aria-pressed={tab === t}
                            className={`h-8 px-3 rounded-[10px] text-[13px] font-medium transition-colors ${tab === t
                                ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'}`}>
                            {t === 'catalog' ? 'Standard frameworks' : 'Custom framework'}
                        </button>
                    ))}
                </div>

                {err && <p role="alert" className="text-xs text-red-700 dark:text-red-300 bg-red-500/[0.06] ring-1 ring-inset ring-red-500/20 px-3 py-2 rounded-lg">{err}</p>}

                {tab === 'catalog' && (
                    <div className="space-y-3">
                        <div className="flex gap-2">
                            <div className="relative flex-1 min-w-0">
                                <SearchIcon size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                                <input
                                    placeholder="Search frameworks…" aria-label="Search frameworks"
                                    value={search} onChange={e => setSearch(e.target.value)}
                                    className={`${fieldCls} w-full pl-9`}
                                />
                            </div>
                            <select value={catFilter} onChange={e => setCatFilter(e.target.value)} aria-label="Category"
                                className={`${fieldCls} flex-shrink-0 pr-8`}>
                                {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                            </select>
                        </div>
                        <ul className="max-h-[50vh] overflow-y-auto space-y-2 pr-1">
                            {filtered.length === 0 && (
                                <li className="text-center text-gray-500 dark:text-gray-400 text-sm py-8">
                                    {existingIds.length >= FRAMEWORK_CATALOG.length ? 'All standard frameworks are already added.' : 'No frameworks match your search.'}
                                </li>
                            )}
                            {filtered.map(f => (
                                <li key={f.id} className="flex items-start justify-between gap-3 p-3 rounded-xl border border-gray-200/80 dark:border-white/[0.07] hover:border-primary-500/40 transition-colors">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-semibold text-sm text-gray-900 dark:text-white">{f.shortName}</span>
                                            <span className="text-[11px] px-2 py-0.5 rounded-full text-gray-600 dark:text-gray-300 bg-gray-500/10">{f.category}</span>
                                            <a href={f.url} target="_blank" rel="noopener noreferrer"
                                                className="text-[11px] text-primary-700 dark:text-primary-300 hover:underline inline-flex items-center gap-0.5">
                                                Official docs <ExternalLinkIcon size={10} />
                                            </a>
                                        </div>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{f.description}</p>
                                    </div>
                                    <button
                                        onClick={() => handleAddCatalog(f)}
                                        disabled={adding === f.id}
                                        aria-label={`Add ${f.shortName}`}
                                        className="flex-shrink-0 inline-flex items-center gap-1 h-8 px-3 text-xs font-semibold text-white rounded-lg bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                                    ><PlusIcon size={12} />{adding === f.id ? 'Adding…' : 'Add'}</button>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {tab === 'custom' && (
                    <div className="space-y-4">
                        {[
                            { label: 'Framework name *', key: 'name', placeholder: 'e.g. Internal Security Policy v2' },
                            { label: 'Short name', key: 'shortName', placeholder: 'e.g. ISP v2' },
                            { label: 'Category', key: 'category', placeholder: 'e.g. Internal, Industry-Specific' },
                            { label: 'Official / reference URL', key: 'official_url', placeholder: 'https://…' },
                        ].map(({ label, key, placeholder }) => (
                            <div key={key}>
                                <label htmlFor={`${fieldId}-${key}`} className={labelCls}>{label}</label>
                                <input
                                    id={`${fieldId}-${key}`}
                                    value={(custom as any)[key]} onChange={e => setCustom({ ...custom, [key]: e.target.value })}
                                    placeholder={placeholder}
                                    className={`${fieldCls} w-full`}
                                />
                            </div>
                        ))}
                        <div>
                            <label htmlFor={`${fieldId}-description`} className={labelCls}>Description</label>
                            <textarea id={`${fieldId}-description`} rows={3} value={custom.description} onChange={e => setCustom({ ...custom, description: e.target.value })}
                                placeholder="Describe the purpose and scope of this framework…"
                                className={`${fieldCls} w-full h-auto py-2 resize-none`} />
                        </div>
                    </div>
                )}
            </div>
        </Modal>
    );
};

// ── Registry ───────────────────────────────────────────────────────────────

const frameworkIcons: Record<string, React.ReactNode> = {
    'iso42001': <BotIcon size={16} />,
    'iso27001': <ShieldLockIcon size={16} />,
    'soc2':     <ShieldCheckIcon size={16} />,
    'gdpr':     <GavelIcon size={16} />,
    'hipaa':    <HeartPulseIcon size={16} />,
    'pci-dss':  <CreditCardIcon size={16} />,
    'nistcsf':  <BookOpenCheckIcon size={16} />,
};

const statusClasses: Record<ComplianceFramework['status'], string> = {
    Compliant:  'text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 ring-emerald-500/20',
    Pending:    'text-amber-700 dark:text-amber-300 bg-amber-500/10 ring-amber-500/20',
    'At Risk':  'text-red-700 dark:text-red-300 bg-red-500/10 ring-red-500/20',
};

// Look up official URL for a framework that's already in the list
const officialUrl = (id: string) => FRAMEWORK_CATALOG.find(f => f.id === id)?.url ?? '';

interface FrameworkRegistryProps {
    frameworks: ComplianceFramework[];
    selectedFramework: ComplianceFramework | null;
    onSelectFramework: (framework: ComplianceFramework) => void;
    onFrameworkAdded?: (f: ComplianceFramework) => void;
}

export const FrameworkRegistry: React.FC<FrameworkRegistryProps> = ({
    frameworks, selectedFramework, onSelectFramework, onFrameworkAdded,
}) => {
    const [showModal, setShowModal] = useState(false);

    return (
        <section aria-label="Frameworks" className="h-full flex flex-col rounded-2xl bg-white dark:bg-gray-800 border border-gray-200/80 dark:border-white/[0.07] shadow-card overflow-hidden">
            <div className="px-5 pt-4 pb-3 border-b border-gray-100 dark:border-white/[0.06] flex items-center justify-between gap-2">
                <h3 className="text-[15px] font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    <ShieldCheckIcon size={16} className="text-primary-500" />
                    Frameworks
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold tabular-nums text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-white/[0.06]">{frameworks.length}</span>
                </h3>
                <button
                    onClick={() => setShowModal(true)}
                    title="Add a compliance framework"
                    className="inline-flex items-center gap-1 h-8 px-3 text-xs font-semibold text-white rounded-lg bg-primary-600 hover:bg-primary-700 transition-colors"
                >
                    <PlusIcon size={13} /> Add
                </button>
            </div>

            {frameworks.length === 0 ? (
                <div className="flex-1 grid place-items-center p-8 text-center">
                    <div>
                        <ShieldCheckIcon size={28} className="mx-auto text-gray-400" />
                        <p className="mt-3 text-sm font-medium text-gray-700 dark:text-gray-300">No frameworks yet</p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Frameworks your organization has purchased appear here.</p>
                    </div>
                </div>
            ) : (
                <ul className="flex-1 overflow-y-auto p-2 space-y-1 max-h-[420px] lg:max-h-none">
                    {frameworks.map(framework => {
                        const link = officialUrl(framework.id) || (framework as any).official_url;
                        const isSelected = selectedFramework?.id === framework.id;
                        const progress = Math.max(0, Math.min(100, Number(framework.progress) || 0));
                        return (
                            <li key={framework.id} className="relative">
                                <button
                                    onClick={() => onSelectFramework(framework)}
                                    aria-current={isSelected ? 'true' : undefined}
                                    className={`w-full text-left pl-3.5 pr-3 py-3 rounded-xl transition-colors duration-150 ${isSelected
                                        ? 'bg-primary-500/[0.08] ring-1 ring-inset ring-primary-500/30 dark:bg-primary-400/10'
                                        : 'hover:bg-gray-100/80 dark:hover:bg-white/[0.04]'}`}
                                >
                                    {isSelected && <span className="absolute left-0 top-3 bottom-3 w-[3px] rounded-full bg-primary-500 dark:bg-primary-400" aria-hidden="true" />}
                                    <div className="flex items-center justify-between gap-2 min-w-0">
                                        <span className="flex items-center gap-2 min-w-0">
                                            <span className="flex-shrink-0 text-primary-600 dark:text-primary-400">{frameworkIcons[framework.id] ?? <ShieldCheckIcon size={16} />}</span>
                                            <span className="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate">{framework.shortName}</span>
                                        </span>
                                        <span className={`flex-shrink-0 px-1.5 py-px rounded-full text-[11px] font-semibold ring-1 ring-inset ${statusClasses[framework.status] ?? statusClasses.Pending}`}>{framework.status}</span>
                                    </div>
                                    <p className={`text-xs text-gray-500 dark:text-gray-400 mt-1 truncate ${link ? 'pr-6' : ''}`}>{framework.name}</p>
                                    <div className="mt-2 flex items-center gap-2" aria-hidden="true">
                                        <div className="flex-1 h-1 rounded-full overflow-hidden bg-gray-200 dark:bg-white/10">
                                            <div className="h-full rounded-full bg-primary-500 dark:bg-primary-400" style={{ width: `${progress}%` }} />
                                        </div>
                                        <span className="text-[11px] tabular-nums text-gray-500 dark:text-gray-400">{progress}%</span>
                                    </div>
                                </button>
                                {link && (
                                    <a
                                        href={link} target="_blank" rel="noopener noreferrer"
                                        aria-label={`${framework.shortName} official documentation`}
                                        title="Official documentation"
                                        className="absolute right-2 top-[30px] grid place-items-center h-6 w-6 rounded-md text-gray-400 hover:text-primary-600 hover:bg-primary-500/10 dark:hover:text-primary-400 transition-colors"
                                    >
                                        <ExternalLinkIcon size={12} />
                                    </a>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}

            {showModal && (
                <AddComplianceModal
                    existingIds={frameworks.map(f => f.id)}
                    onClose={() => setShowModal(false)}
                    onAdded={f => { onFrameworkAdded?.(f); setShowModal(false); }}
                />
            )}
        </section>
    );
};
