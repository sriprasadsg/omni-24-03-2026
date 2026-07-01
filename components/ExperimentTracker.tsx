
import React from 'react';
import { ModelExperiment } from '../types';
// FIX: Added missing FlaskConicalIcon.
import { FlaskConicalIcon } from './icons';

interface ExperimentTrackerProps {
    experiments: ModelExperiment[];
}

const statusClasses: Record<ModelExperiment['status'], string> = {
    Running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
    Completed: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
    Failed: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
};

export const ExperimentTracker: React.FC<ExperimentTrackerProps> = ({ experiments }) => {
    return (
         <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold flex items-center">
                    <FlaskConicalIcon className="mr-2 text-primary-500" />
                    Model Experiments
                </h3>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                    <thead className="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                        <tr>
                            <th scope="col" className="px-6 py-3">Experiment ID</th>
                            <th scope="col" className="px-6 py-3">Model</th>
                            <th scope="col" className="px-6 py-3">Status</th>
                            <th scope="col" className="px-6 py-3">Accuracy</th>
                            <th scope="col" className="px-6 py-3">Precision</th>
                            <th scope="col" className="px-6 py-3">F1-Score</th>
                            <th scope="col" className="px-6 py-3">Created</th>
                            <th scope="col" className="px-6 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {experiments.map(exp => (
                            <tr key={exp.id} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/50">
                                <td className="px-6 py-4 font-mono text-xs font-medium text-gray-900 dark:text-white">{exp.id}</td>
                                <td className="px-6 py-4">{exp.modelName}</td>
                                <td className="px-6 py-4">
                                    <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusClasses[exp.status]}`}>{exp.status}</span>
                                </td>
                                <td className="px-6 py-4 font-semibold">{exp.metrics.accuracy.toFixed(4)}</td>
                                <td className="px-6 py-4">{exp.metrics.precision.toFixed(4)}</td>
                                <td className="px-6 py-4">{exp.metrics.f1Score.toFixed(4)}</td>
                                <td className="px-6 py-4">{new Date(exp.createdAt).toLocaleDateString()}</td>
                                <td className="px-6 py-4">
                                     <button disabled={exp.status !== 'Completed'} className="px-2.5 py-1 text-xs font-medium text-primary-700 bg-primary-100 rounded-md hover:bg-primary-200 disabled:opacity-50 disabled:cursor-not-allowed">Register Model</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
