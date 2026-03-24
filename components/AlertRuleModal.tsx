import React, { useState, useEffect } from 'react';
import { AlertRule, MetricType, AlertSeverity } from '../types';

interface AlertRuleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (rule: AlertRule) => void;
  rule: AlertRule | null;
}

const metricOptions: MetricType[] = ['cpu', 'memory', 'disk', 'network', 'security_event'];
const severityOptions: AlertSeverity[] = ['Critical', 'High', 'Medium', 'Low'];
const conditionOptions: AlertRule['condition'][] = ['>', '<', '=='];

const defaultRule: Omit<AlertRule, 'id'> = {
    name: '',
    metric: 'cpu',
    condition: '>',
    threshold: 80,
    duration: 5,
    severity: 'High',
    isEnabled: true
};

export const AlertRuleModal: React.FC<AlertRuleModalProps> = ({ isOpen, onClose, onSave, rule }) => {
  const [formData, setFormData] = useState<Omit<AlertRule, 'id'>>(defaultRule);

  useEffect(() => {
    if (isOpen) {
        if (rule) {
            setFormData({ ...rule });
        } else {
            setFormData(defaultRule);
        }
    }
  }, [rule, isOpen]);
  
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    let finalValue: string | number | boolean = value;

    if (type === 'number') {
        finalValue = value === '' ? '' : Number(value);
    } else if (name === 'isEnabled') {
        finalValue = (e.target as HTMLInputElement).checked;
    }

    setFormData(prev => ({ ...prev, [name]: finalValue }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const ruleToSave: AlertRule = {
      id: rule?.id || `rule-${new Date().getTime()}`,
      ...formData,
      threshold: Number(formData.threshold), // ensure it's a number
      duration: formData.duration ? Number(formData.duration) : undefined,
    };
    onSave(ruleToSave);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">{rule ? 'Edit Alert Rule' : 'Create New Alert Rule'}</h2>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Rule Name</label>
              <input type="text" name="name" value={formData.name} onChange={handleChange} required className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md" />
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                    <label htmlFor="metric" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Metric</label>
                    <select name="metric" value={formData.metric} onChange={handleChange} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md">
                        {metricOptions.map(opt => <option key={opt} value={opt}>{opt.toUpperCase()}</option>)}
                    </select>
                </div>
                 <div>
                    <label htmlFor="condition" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Condition</label>
                    <select name="condition" value={formData.condition} onChange={handleChange} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md">
                        {conditionOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                    </select>
                </div>
                 <div>
                    <label htmlFor="threshold" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Threshold</label>
                    <input type="number" name="threshold" value={formData.threshold} onChange={handleChange} required className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md" />
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label htmlFor="duration" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Duration (mins)</label>
                    <input type="number" name="duration" value={formData.duration || ''} onChange={handleChange} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md" />
                </div>
                 <div>
                    <label htmlFor="severity" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Severity</label>
                    <select name="severity" value={formData.severity} onChange={handleChange} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md">
                        {severityOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                    </select>
                </div>
            </div>

            <div className="flex items-center">
                <input type="checkbox" name="isEnabled" checked={formData.isEnabled} onChange={handleChange} className="h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500" />
                <label htmlFor="isEnabled" className="ml-2 block text-sm text-gray-900 dark:text-gray-300">Enable this rule</label>
            </div>
          </div>
          <div className="mt-6 flex justify-end space-x-3">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
            <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Save Rule</button>
          </div>
        </form>
      </div>
    </div>
  );
};
