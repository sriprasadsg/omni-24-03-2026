import React, { useState } from 'react';
import { ServiceTemplate, ProvisionedService } from '../types';
import { PuzzleIcon, CheckIcon, CogIcon } from './icons';

interface ServiceCatalogDashboardProps {
    templates: ServiceTemplate[];
    provisionedServices: ProvisionedService[];
}

export const ServiceCatalogDashboard: React.FC<ServiceCatalogDashboardProps> = ({ templates, provisionedServices }) => {
    const [isProvisioning, setIsProvisioning] = useState<string | null>(null);
    const [provisioned, setProvisioned] = useState<string[]>([]);

    const handleProvision = (templateId: string) => {
        setIsProvisioning(templateId);
        setTimeout(() => {
            setIsProvisioning(null);
            setProvisioned(prev => [...prev, templateId]);
        }, 3000);
    };

    return (
        <div className="space-y-8 animate-fade-in p-2">
            <header>
                <h2 className="text-4xl font-bold bg-gradient-to-r from-primary-600 via-indigo-600 to-accent-600 bg-clip-text text-transparent flex items-center gap-3">
                    <PuzzleIcon size={36} className="text-primary-500" />
                    Service Catalog (IDP)
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-2 text-lg">
                    Provision new services using approved, secure-by-default templates.
                </p>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                {(!templates || templates.length === 0) ? (
                    <div className="col-span-full glass-premium rounded-3xl p-12 text-center">
                        <PuzzleIcon size={48} className="mx-auto text-gray-400 opacity-20 mb-4" />
                        <p className="text-xl font-bold text-gray-800 dark:text-gray-100 italic uppercase tracking-tighter">No Service Templates Found</p>
                        <p className="text-sm text-gray-500 mt-2">Templates will appear here once configured by your platform administrator.</p>
                    </div>
                ) : (
                    templates.map(template => (
                        <div key={template.id} className="glass-premium rounded-3xl p-8 flex flex-col hover:scale-[1.02] transition-all border border-white/10 group relative overflow-hidden">
                            <div className="absolute top-0 right-0 p-4">
                                <span className="px-2 py-1 bg-primary-500/10 text-primary-500 rounded text-[10px] font-black uppercase tracking-widest border border-primary-500/20">Template</span>
                            </div>
                            <div className="flex-grow">
                                <h3 className="text-2xl font-black text-gray-800 dark:text-gray-100 flex items-center gap-3 italic uppercase tracking-tighter">
                                    <PuzzleIcon className="text-primary-500" />
                                    {template.name}
                                </h3>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-4 leading-relaxed line-clamp-2">{template.description}</p>
                                <div className="mt-6 flex flex-wrap gap-2">
                                    {template.tags.map(tag => (
                                        <span key={tag} className="px-3 py-1 text-[10px] font-black rounded-lg bg-black/5 dark:bg-white/10 text-gray-500 dark:text-gray-400 uppercase tracking-widest border border-white/5">{tag}</span>
                                    ))}
                                </div>
                            </div>
                            <div className="mt-8 pt-6 border-t border-white/10">
                                <button
                                    onClick={() => handleProvision(template.id)}
                                    disabled={isProvisioning === template.id || provisioned.includes(template.id)}
                                    className={`w-full flex items-center justify-center gap-3 px-6 py-3 text-sm font-black rounded-xl transition-all shadow-lg ${isProvisioning === template.id ? 'bg-indigo-600 text-white animate-pulse' :
                                            provisioned.includes(template.id) ? 'bg-green-600 text-white shadow-green-500/30' :
                                                'bg-primary-600 hover:bg-primary-700 text-white shadow-primary-500/30'
                                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                                >
                                    {isProvisioning === template.id ? (
                                        <><CogIcon size={20} className="animate-spin" /> Provisioning...</>
                                    ) : provisioned.includes(template.id) ? (
                                        <><CheckIcon size={20} /> Deployment Ready</>
                                    ) : (
                                        'Provision System'
                                    )}
                                </button>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};
