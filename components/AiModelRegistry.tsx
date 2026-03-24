import React, { useState, useEffect } from 'react';
import { AiModel, fetchAiModels, registerAiModel } from '../services/apiService';
import { PlusIcon, ServerIcon, ClockIcon, AlertTriangleIcon, SearchIcon, LayersIcon, ShieldCheckIcon, SparklesIcon } from './icons';

interface AiModelRegistryProps {
    onEvaluate?: (modelId: string) => void;
    onExpertEvaluate?: (modelId: string) => void;
}

export const AiModelRegistry: React.FC<AiModelRegistryProps> = ({ onEvaluate, onExpertEvaluate }) => {
    const [models, setModels] = useState<AiModel[]>([]);
    const [showRegisterModal, setShowRegisterModal] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadModels();
    }, []);

    const loadModels = async () => {
        setLoading(true);
        const data = await fetchAiModels();
        setModels(data);
        setLoading(false);
    };

    const handleRegister = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const formData = new FormData(e.currentTarget);
        const newModel: Partial<AiModel> = {
            id: `model-${Date.now()}`,
            name: formData.get('name') as string,
            tenantId: 'default',
            description: formData.get('description') as string,
            framework: formData.get('framework') as string,
            type: formData.get('type') as string,
            owner: 'admin', // mock
            riskLevel: formData.get('riskLevel') as any,
            versions: [
                {
                    version: 'v1.0',
                    createdAt: new Date().toISOString(),
                    createdBy: 'admin',
                    status: 'Staging',
                    metrics: { accuracy: 0.85, latency: 150 }
                }
            ],
            currentVersion: 'v1.0',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
        };

        try {
            await registerAiModel(newModel);
            setShowRegisterModal(false);
            loadModels();
        } catch (error) {
            console.error(error);
            alert("Failed to register model");
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-white">AI Model Registry</h2>
                    <p className="text-gray-500 dark:text-gray-400">Track and version control your AI assets</p>
                </div>
                <button
                    onClick={() => setShowRegisterModal(true)}
                    className="flex items-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
                >
                    <PlusIcon size={20} className="mr-2" />
                    Register Model
                </button>
            </div>

            {/* Model List */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {models.map(model => (
                    <div key={model.id} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5 hover:shadow-md transition-shadow flex flex-col">
                        <div className="flex justify-between items-start mb-4">
                            <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-lg">
                                <LayersIcon size={24} />
                            </div>
                            <span className={`px-2 py-1 text-xs font-semibold rounded-full ${model.riskLevel === 'High' || model.riskLevel === 'Critical' ? 'bg-red-100 text-red-800' :
                                model.riskLevel === 'Medium' ? 'bg-yellow-100 text-yellow-800' :
                                    'bg-green-100 text-green-800'
                                }`}>
                                {model.riskLevel} Risk
                            </span>
                        </div>

                        <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-2">{model.name}</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 line-clamp-2 flex-grow">{model.description}</p>

                        <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300 mb-4">
                            <div className="flex items-center">
                                <ServerIcon size={14} className="mr-2 opacity-70" />
                                {model.framework} • {model.type}
                            </div>
                            <div className="flex items-center">
                                <ClockIcon size={14} className="mr-2 opacity-70" />
                                V: {model.currentVersion || 'v1.0'}
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <button
                                onClick={() => onEvaluate && onEvaluate(model.id)}
                                className="w-full py-2 bg-gray-50 dark:bg-gray-900/50 text-primary-600 dark:text-primary-400 text-sm font-bold rounded-lg border border-gray-100 dark:border-gray-800 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors flex items-center justify-center"
                            >
                                <ShieldCheckIcon size={16} className="mr-2" />
                                Rule Check
                            </button>
                            <button
                                onClick={() => onExpertEvaluate && onExpertEvaluate(model.id)}
                                className="w-full py-2 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 text-sm font-bold rounded-lg border border-indigo-100 dark:border-indigo-900/30 hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors flex items-center justify-center"
                            >
                                <SparklesIcon size={16} className="mr-2" />
                                AI Expert
                            </button>
                        </div>
                    </div>
                ))}
            </div>

            {/* Empty State */}
            {!loading && models.length === 0 && (
                <div className="text-center py-20 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-dashed border-gray-300 dark:border-gray-700">
                    <LayersIcon size={48} className="mx-auto text-gray-400 mb-4" />
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white">No models registered</h3>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">Register your first AI model to start tracking.</p>
                </div>
            )}

            {/* Check Model Modal */}
            {showRegisterModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
                        <h3 className="text-xl font-bold mb-4 text-gray-900 dark:text-white">Register New Model</h3>
                        <form onSubmit={handleRegister} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1 dark:text-gray-300">Model Name</label>
                                <input name="name" required className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1 dark:text-gray-300">Description</label>
                                <textarea name="description" className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1 dark:text-gray-300">Framework</label>
                                    <select name="framework" className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                        <option>PyTorch</option>
                                        <option>TensorFlow</option>
                                        <option>Scikit-Learn</option>
                                        <option>Other</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1 dark:text-gray-300">Type</label>
                                    <select name="type" className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                        <option>LLM</option>
                                        <option>Classification</option>
                                        <option>Regression</option>
                                        <option>Computer Vision</option>
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1 dark:text-gray-300">Initial Risk Assessment</label>
                                <select name="riskLevel" className="w-full p-2 border rounded dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                    <option>Low</option>
                                    <option>Medium</option>
                                    <option>High</option>
                                    <option>Critical</option>
                                </select>
                            </div>
                            <div className="flex justify-end space-x-3 mt-6">
                                <button type="button" onClick={() => setShowRegisterModal(false)} className="px-4 py-2 text-gray-600 hover:text-gray-800 dark:text-gray-400">Cancel</button>
                                <button type="submit" className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-700">Register</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};
