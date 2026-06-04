import React, { useState } from 'react';
import { ComplianceFramework } from '../types';
import { ShieldCheckIcon, BotIcon, ShieldLockIcon, GavelIcon, HeartPulseIcon, CreditCardIcon, BookOpenCheckIcon, PlusIcon, XIcon, ExternalLinkIcon } from './icons';
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

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                    <h2 className="text-lg font-bold text-gray-900 dark:text-white">Add Compliance Framework</h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"><XIcon size={20} /></button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-gray-200 dark:border-gray-700 px-6">
                    {(['catalog', 'custom'] as const).map(t => (
                        <button key={t} onClick={() => setTab(t)}
                            className={`py-3 px-4 text-sm font-medium border-b-2 -mb-px capitalize transition-colors ${tab === t ? 'border-primary-500 text-primary-600 dark:text-primary-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'}`}>
                            {t === 'catalog' ? '📋 Standard Frameworks' : '✏️ Custom Framework'}
                        </button>
                    ))}
                </div>

                {err && <p className="mx-6 mt-3 text-red-600 dark:text-red-400 text-xs bg-red-50 dark:bg-red-900/20 px-3 py-2 rounded-lg">{err}</p>}

                {/* Catalog tab */}
                {tab === 'catalog' && (
                    <div className="flex flex-col flex-1 overflow-hidden px-6 py-4 gap-3">
                        <div className="flex gap-2">
                            <input
                                placeholder="Search frameworks…"
                                value={search} onChange={e => setSearch(e.target.value)}
                                className="flex-1 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white focus:outline-none focus:border-primary-500"
                            />
                            <select value={catFilter} onChange={e => setCatFilter(e.target.value)}
                                className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white">
                                {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                            </select>
                        </div>
                        <div className="overflow-y-auto flex-1 space-y-2 pr-1">
                            {filtered.length === 0 && (
                                <p className="text-center text-gray-400 dark:text-gray-500 text-sm py-8">
                                    {existingIds.length >= FRAMEWORK_CATALOG.length ? 'All standard frameworks are already added.' : 'No frameworks match your search.'}
                                </p>
                            )}
                            {filtered.map(f => (
                                <div key={f.id} className="flex items-start justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-primary-300 dark:hover:border-primary-600 transition-colors">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-semibold text-sm text-gray-900 dark:text-white">{f.shortName}</span>
                                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">{f.category}</span>
                                            <a href={f.url} target="_blank" rel="noopener noreferrer"
                                                onClick={e => e.stopPropagation()}
                                                className="text-[10px] text-primary-500 hover:text-primary-700 flex items-center gap-0.5">
                                                Official Docs <ExternalLinkIcon size={10} />
                                            </a>
                                        </div>
                                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">{f.description}</p>
                                    </div>
                                    <button
                                        onClick={() => handleAddCatalog(f)}
                                        disabled={adding === f.id}
                                        className="flex-shrink-0 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50"
                                    >{adding === f.id ? 'Adding…' : '+ Add'}</button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Custom tab */}
                {tab === 'custom' && (
                    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
                        {[
                            { label: 'Framework Name *', key: 'name', placeholder: 'e.g. Internal Security Policy v2' },
                            { label: 'Short Name', key: 'shortName', placeholder: 'e.g. ISP v2' },
                            { label: 'Category', key: 'category', placeholder: 'e.g. Internal, Industry-Specific' },
                            { label: 'Official / Reference URL', key: 'official_url', placeholder: 'https://…' },
                        ].map(({ label, key, placeholder }) => (
                            <div key={key}>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{label}</label>
                                <input
                                    value={(custom as any)[key]} onChange={e => setCustom({ ...custom, [key]: e.target.value })}
                                    placeholder={placeholder}
                                    className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white focus:outline-none focus:border-primary-500"
                                />
                            </div>
                        ))}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                            <textarea rows={3} value={custom.description} onChange={e => setCustom({ ...custom, description: e.target.value })}
                                placeholder="Describe the purpose and scope of this framework…"
                                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white focus:outline-none focus:border-primary-500 resize-none" />
                        </div>
                        <div className="flex justify-end gap-3 pt-2">
                            <button onClick={onClose} className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 rounded-lg">Cancel</button>
                            <button onClick={handleAddCustom} disabled={adding === 'custom'}
                                className="px-4 py-2 text-sm text-white bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50 flex items-center gap-1.5">
                                <PlusIcon size={14} />
                                {adding === 'custom' ? 'Creating…' : 'Create Framework'}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

// ── Registry ───────────────────────────────────────────────────────────────

const frameworkIcons: Record<string, React.ReactNode> = {
    'iso42001': <BotIcon size={20} />,
    'iso27001': <ShieldLockIcon size={20} />,
    'soc2':     <ShieldCheckIcon size={20} />,
    'gdpr':     <GavelIcon size={20} />,
    'hipaa':    <HeartPulseIcon size={20} />,
    'pci-dss':  <CreditCardIcon size={20} />,
    'nistcsf':  <BookOpenCheckIcon size={20} />,
};

const statusClasses: Record<ComplianceFramework['status'], string> = {
    Compliant:  'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    Pending:    'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
    'At Risk':  'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
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
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md h-full flex flex-col">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between mb-1">
                    <h3 className="text-lg font-semibold flex items-center">
                        <ShieldCheckIcon className="mr-2 text-primary-500" />
                        Frameworks
                    </h3>
                    <button
                        onClick={() => setShowModal(true)}
                        title="Add a compliance framework"
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors"
                    >
                        <PlusIcon size={13} /> Add
                    </button>
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500">{frameworks.length} framework{frameworks.length !== 1 ? 's' : ''} active</p>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-2">
                {frameworks.map(framework => {
                    const link = officialUrl(framework.id) || (framework as any).official_url;
                    return (
                        <button
                            key={framework.id}
                            onClick={() => onSelectFramework(framework)}
                            className={`w-full text-left p-3 rounded-lg transition-colors duration-150 ${
                                selectedFramework?.id === framework.id
                                    ? 'bg-primary-100 dark:bg-primary-900/50 ring-2 ring-primary-500'
                                    : 'hover:bg-gray-100 dark:hover:bg-gray-700/50'
                            }`}
                        >
                            <div className="flex justify-between items-start">
                                <div className="flex items-center">
                                    <span className="text-primary-500 w-5">{frameworkIcons[framework.id] ?? <ShieldCheckIcon size={20} />}</span>
                                    <p className="ml-2 font-semibold text-gray-800 dark:text-gray-100 text-sm">{framework.shortName}</p>
                                </div>
                                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${statusClasses[framework.status]}`}>{framework.status}</span>
                            </div>
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">{framework.name}</p>
                            {link && (
                                <a
                                    href={link} target="_blank" rel="noopener noreferrer"
                                    onClick={e => e.stopPropagation()}
                                    className="mt-1 inline-flex items-center gap-0.5 text-[10px] text-primary-500 hover:text-primary-700"
                                >
                                    Official Docs <ExternalLinkIcon size={10} />
                                </a>
                            )}
                        </button>
                    );
                })}
            </div>

            {showModal && (
                <AddComplianceModal
                    existingIds={frameworks.map(f => f.id)}
                    onClose={() => setShowModal(false)}
                    onAdded={f => { onFrameworkAdded?.(f); setShowModal(false); }}
                />
            )}
        </div>
    );
};
