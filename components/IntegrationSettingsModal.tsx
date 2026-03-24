
import React, { useState, useEffect } from 'react';
import { Integration, SlackIntegrationConfig, PagerDutyIntegrationConfig, JiraIntegrationConfig, AlertSeverity } from '../types';
import { XIcon, CogIcon, CheckIcon, AlertTriangleIcon } from './icons';
import * as apiService from '../services/apiService';

interface IntegrationSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  integration: Integration | null;
  onSave: (updatedIntegration: Integration) => void;
}

const severityOptions: AlertSeverity[] = ['Critical', 'High', 'Medium', 'Low'];

const notificationTypeOptions: Record<string, string> = {
  alerts: 'System Alerts',
  security: 'Security Events',
  compliance: 'Compliance Reminders',
  ai: 'AI Governance Risks'
};


// Validation function
const validate = (config: Integration['config'], type: Integration['id']): Record<string, string> => {
  const newErrors: Record<string, string> = {};
  const urlRegex = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([/\w .-]*)*\/?$/;

  switch (type) {
    case 'slack':
      const slackConfig = config as SlackIntegrationConfig;
      if (!slackConfig.webhookUrl || !slackConfig.webhookUrl.startsWith('https://hooks.slack.com/services/')) {
        newErrors.webhookUrl = 'Please enter a valid Slack webhook URL starting with https://hooks.slack.com/...';
      }
      if (!slackConfig.channel || !slackConfig.channel.startsWith('#')) {
        newErrors.channel = 'Channel name must start with a # symbol.';
      }
      break;
    case 'pagerduty':
      const pagerDutyConfig = config as PagerDutyIntegrationConfig;
      if (!pagerDutyConfig.apiKey || pagerDutyConfig.apiKey.trim() === '') {
        newErrors.apiKey = 'API Key cannot be empty.';
      } else if (pagerDutyConfig.apiKey.length < 20) {
        newErrors.apiKey = 'This does not appear to be a valid PagerDuty API key.';
      }
      break;
    case 'jira':
      const jiraConfig = config as JiraIntegrationConfig;
      if (!jiraConfig.apiUrl || !urlRegex.test(jiraConfig.apiUrl)) {
        newErrors.apiUrl = 'Please enter a valid URL for your Jira instance.';
      }
      if (!jiraConfig.apiToken || jiraConfig.apiToken.trim() === '') {
        newErrors.apiToken = 'API Token cannot be empty.';
      }
      if (!jiraConfig.projectKey || jiraConfig.projectKey.trim() === '') {
        newErrors.projectKey = 'Project Key cannot be empty.';
      }
      break;
    case 'splunk':
      const splunkConfig = config as any;
      if (!splunkConfig.url || !urlRegex.test(splunkConfig.url)) {
        newErrors.url = 'Please enter a valid Splunk HEC URL.';
      }
      if (!splunkConfig.token) {
        newErrors.token = 'HEC Token cannot be empty.';
      }
      break;
    case 'datadog':
      const datadogConfig = config as any;
      if (!datadogConfig.apiKey) newErrors.apiKey = 'API Key is required.';
      if (!datadogConfig.appKey) newErrors.appKey = 'Application Key is required.';
      break;
    case 'crowdstrike':
      const crowdstrikeConfig = config as any;
      if (!crowdstrikeConfig.clientId) newErrors.clientId = 'Client ID is required.';
      if (!crowdstrikeConfig.clientSecret) newErrors.clientSecret = 'Client Secret is required.';
      break;
    case 'elk' as any:
      const elkConfig = config as any;
      if (!elkConfig.endpoint || !urlRegex.test(elkConfig.endpoint)) {
        newErrors.endpoint = 'Please enter a valid Elasticsearch/Logstash URL.';
      }
      if (!elkConfig.index) {
        newErrors.index = 'Index name is required.';
      }
      break;
  }
  return newErrors;
};


export const IntegrationSettingsModal: React.FC<IntegrationSettingsModalProps> = ({ isOpen, onClose, integration, onSave }) => {
  const [currentConfig, setCurrentConfig] = useState<Integration['config'] | undefined>(undefined);
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'failed'>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (integration) {
      setCurrentConfig(JSON.parse(JSON.stringify(integration.config))); // Deep copy
      setTestStatus('idle');
      setTestMessage('');
      setErrors({}); // Reset errors on modal open
    }
  }, [integration]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setCurrentConfig(prev => prev ? { ...prev, [name]: value } : undefined);
    setTestStatus('idle');
    setTestMessage('');
    // Clear the error for the field being edited
    if (errors[name]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, checked } = e.target;
    setCurrentConfig(prev => {
      if (!prev) return undefined;
      const slackConfig = prev as SlackIntegrationConfig;
      const currentTypes = slackConfig.notificationTypes || [];
      if (checked) {
        return { ...slackConfig, notificationTypes: [...currentTypes, name] };
      } else {
        return { ...slackConfig, notificationTypes: currentTypes.filter(type => type !== name) };
      }
    });
    setTestStatus('idle');
    setTestMessage('');
  };

  const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (currentConfig && integration) {
      const { name } = e.target;
      const validationErrors = validate(currentConfig, integration.id);
      setErrors(prev => ({ ...prev, [name]: validationErrors[name] }));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (integration && currentConfig) {
      const validationErrors = validate(currentConfig, integration.id);
      if (Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors);
        return;
      }

      // For known types, we cast. For others, we just pass the config object (it's 'any' effectively in the store)
      const finalIntegration = { ...integration, config: currentConfig };
      onSave(finalIntegration);
    }
  };

  const handleTestConnection = async () => {
    if (!integration || !currentConfig) return;

    const validationErrors = validate(currentConfig, integration.id);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      setTestStatus('failed');
      setTestMessage('Please fix the validation errors before testing.');
      return;
    }

    setTestStatus('testing');
    setTestMessage('');

    try {
      const result = await apiService.testSiemConnection(integration.id, currentConfig);
      if (result.success) {
        setTestStatus('success');
        setTestMessage(result.message || `Successfully connected to ${integration.name}.`);
      } else {
        setTestStatus('failed');
        setTestMessage(result.error || `Failed to connect to ${integration.name}.`);
      }
    } catch (error) {
      setTestStatus('failed');
      setTestMessage(error instanceof Error ? error.message : 'An unexpected error occurred.');
    }
  };

  if (!isOpen || !integration || !currentConfig) return null;

  const hasErrors = Object.keys(errors).some(key => errors[key]);

  const renderForm = () => {
    switch (integration.id) {
      case 'slack':
        const slackConfig = currentConfig as SlackIntegrationConfig;
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="webhookUrl" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Webhook URL</label>
              <input
                type="text"
                name="webhookUrl"
                id="webhookUrl"
                value={slackConfig.webhookUrl || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.webhookUrl ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.webhookUrl && <p className="mt-1 text-xs text-red-500">{errors.webhookUrl}</p>}
            </div>
            <div>
              <label htmlFor="channel" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Notification Channel</label>
              <input
                type="text"
                name="channel"
                id="channel"
                value={slackConfig.channel || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                placeholder="#alerts-critical"
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.channel ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.channel && <p className="mt-1 text-xs text-red-500">{errors.channel}</p>}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="severityThreshold" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Minimum Alert Severity</label>
                <select
                  name="severityThreshold"
                  id="severityThreshold"
                  value={slackConfig.severityThreshold || 'High'}
                  onChange={handleChange}
                  className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                >
                  {severityOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Notification Types</label>
              <fieldset className="mt-2 space-y-2 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-md border border-gray-200 dark:border-gray-600">
                <legend className="sr-only">Notification Types</legend>
                {Object.entries(notificationTypeOptions).map(([key, label]) => (
                  <label key={key} className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      name={key}
                      checked={slackConfig.notificationTypes?.includes(key)}
                      onChange={handleCheckboxChange}
                      className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                    />
                    <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
                  </label>
                ))}
              </fieldset>
            </div>
          </div>
        );
      case 'pagerduty':
        const pagerDutyConfig = currentConfig as PagerDutyIntegrationConfig;
        return (
          <div>
            <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 dark:text-gray-300">API Key</label>
            <input
              type="password"
              name="apiKey"
              id="apiKey"
              value={pagerDutyConfig.apiKey || ''}
              onChange={handleChange}
              onBlur={handleBlur}
              required
              placeholder="••••••••••••••••••••"
              className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.apiKey ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
            />
            {errors.apiKey && <p className="mt-1 text-xs text-red-500">{errors.apiKey}</p>}
          </div>
        );
      case 'jira':
        const jiraConfig = currentConfig as JiraIntegrationConfig;
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="apiUrl" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Jira API URL</label>
              <input
                type="text"
                name="apiUrl"
                id="apiUrl"
                value={jiraConfig.apiUrl || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.apiUrl ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.apiUrl && <p className="mt-1 text-xs text-red-500">{errors.apiUrl}</p>}
            </div>
            <div>
              <label htmlFor="apiToken" className="block text-sm font-medium text-gray-700 dark:text-gray-300">API Token</label>
              <input
                type="password"
                name="apiToken"
                id="apiToken"
                value={jiraConfig.apiToken || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                placeholder="••••••••••••••••••••"
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.apiToken ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.apiToken && <p className="mt-1 text-xs text-red-500">{errors.apiToken}</p>}
            </div>
            <div>
              <label htmlFor="projectKey" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Project Key</label>
              <input
                type="text"
                name="projectKey"
                id="projectKey"
                value={jiraConfig.projectKey || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.projectKey ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.projectKey && <p className="mt-1 text-xs text-red-500">{errors.projectKey}</p>}
            </div>
          </div>
        );
      case 'splunk':
        const splunkConfig = currentConfig as any;
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="url" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Splunk HEC URL</label>
              <input
                type="text"
                name="url"
                id="url"
                value={splunkConfig.url || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                placeholder="https://splunk.example.com:8088"
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.url ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.url && <p className="mt-1 text-xs text-red-500">{errors.url}</p>}
            </div>
            <div>
              <label htmlFor="token" className="block text-sm font-medium text-gray-700 dark:text-gray-300">HEC Token</label>
              <input
                type="password"
                name="token"
                id="token"
                value={splunkConfig.token || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.token ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.token && <p className="mt-1 text-xs text-red-500">{errors.token}</p>}
            </div>
          </div>
        );
      case 'datadog':
        const datadogConfig = currentConfig as any;
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700 dark:text-gray-300">API Key</label>
              <input
                type="password"
                name="apiKey"
                id="apiKey"
                value={datadogConfig.apiKey || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.apiKey ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.apiKey && <p className="mt-1 text-xs text-red-500">{errors.apiKey}</p>}
            </div>
            <div>
              <label htmlFor="appKey" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Application Key</label>
              <input
                type="password"
                name="appKey"
                id="appKey"
                value={datadogConfig.appKey || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.appKey ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.appKey && <p className="mt-1 text-xs text-red-500">{errors.appKey}</p>}
            </div>
          </div>
        );
      case 'crowdstrike':
        const crowdstrikeConfig = currentConfig as any;
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="clientId" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Client ID</label>
              <input
                type="text"
                name="clientId"
                id="clientId"
                value={crowdstrikeConfig.clientId || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.clientId ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.clientId && <p className="mt-1 text-xs text-red-500">{errors.clientId}</p>}
            </div>
            <div>
              <label htmlFor="clientSecret" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Client Secret</label>
              <input
                type="password"
                name="clientSecret"
                id="clientSecret"
                value={crowdstrikeConfig.clientSecret || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.clientSecret ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.clientSecret && <p className="mt-1 text-xs text-red-500">{errors.clientSecret}</p>}
            </div>
          </div>
        );
      case 'elk' as any:
        const elkConfig = currentConfig as any;
        return (
          <div className="space-y-4">
            <div>
              <label htmlFor="endpoint" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Elasticsearch/Logstash Endpoint</label>
              <input
                type="text"
                name="endpoint"
                id="endpoint"
                value={elkConfig.endpoint || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                placeholder="https://elk.example.com:9200"
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.endpoint ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.endpoint && <p className="mt-1 text-xs text-red-500">{errors.endpoint}</p>}
            </div>
            <div>
              <label htmlFor="index" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Index Name</label>
              <input
                type="text"
                name="index"
                id="index"
                value={elkConfig.index || 'security-events'}
                onChange={handleChange}
                onBlur={handleBlur}
                required
                className={`mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border rounded-md shadow-sm sm:text-sm ${errors.index ? 'border-red-500 focus:ring-red-500 focus:border-red-500' : 'border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-primary-500 focus:border-primary-500'}`}
              />
              {errors.index && <p className="mt-1 text-xs text-red-500">{errors.index}</p>}
            </div>
            <div>
              <label htmlFor="api_key" className="block text-sm font-medium text-gray-700 dark:text-gray-300">API Key (Optional)</label>
              <input
                type="password"
                name="api_key"
                id="api_key"
                value={elkConfig.api_key || ''}
                onChange={handleChange}
                onBlur={handleBlur}
                className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
              />
            </div>
          </div>
        );
      default:
        // Generic config editor for custom / community / unknown integration types
        const genericConfig = currentConfig as Record<string, string>;
        const knownKeys = Object.keys(genericConfig).filter(k => k !== '__type__');
        return (
          <div className="space-y-4">
            <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50 rounded-md p-3 border border-gray-200 dark:border-gray-600">
              Configure credentials and settings for <strong>{integration.name}</strong>. Add key-value pairs for any required configuration fields.
            </p>
            {knownKeys.length > 0 ? (
              knownKeys.map(key => (
                <div key={key}>
                  <label htmlFor={`generic-${key}`} className="block text-sm font-medium capitalize text-gray-700 dark:text-gray-300">
                    {key.replace(/_/g, ' ')}
                  </label>
                  <input
                    type={key.toLowerCase().includes('secret') || key.toLowerCase().includes('token') || key.toLowerCase().includes('password') || key.toLowerCase().includes('key') ? 'password' : 'text'}
                    id={`generic-${key}`}
                    name={key}
                    value={genericConfig[key] || ''}
                    onChange={handleChange}
                    className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                  />
                </div>
              ))
            ) : (
              <div className="space-y-3">
                <div>
                  <label htmlFor="generic-url" className="block text-sm font-medium text-gray-700 dark:text-gray-300">URL / Endpoint</label>
                  <input type="text" id="generic-url" name="url" value={genericConfig.url || ''} onChange={handleChange} placeholder="https://..." className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm" />
                </div>
                <div>
                  <label htmlFor="generic-api_key" className="block text-sm font-medium text-gray-700 dark:text-gray-300">API Key / Token</label>
                  <input type="password" id="generic-api_key" name="api_key" value={genericConfig.api_key || ''} onChange={handleChange} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm" />
                </div>
                <div>
                  <label htmlFor="generic-username" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Username (Optional)</label>
                  <input type="text" id="generic-username" name="username" value={genericConfig.username || ''} onChange={handleChange} className="mt-1 block w-full px-3 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm" />
                </div>
              </div>
            )}
          </div>
        );
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">Configure {integration.name}</h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none">
            <XIcon size={20} />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            {renderForm()}
          </div>

          {testStatus !== 'idle' && (
            <div className={`mt-4 p-3 rounded-md text-sm flex items-start ${testStatus === 'success' ? 'bg-green-50 dark:bg-green-900/50' :
              testStatus === 'failed' ? 'bg-red-50 dark:bg-red-900/50' :
                'bg-gray-100 dark:bg-gray-700/50'
              }`}>
              {testStatus === 'testing' && <CogIcon size={18} className="animate-spin mr-2 mt-0.5 text-gray-500" />}
              {testStatus === 'success' && <CheckIcon size={18} className="mr-2 mt-0.5 text-green-500" />}
              {testStatus === 'failed' && <AlertTriangleIcon size={18} className="mr-2 mt-0.5 text-red-500" />}
              <p className={
                testStatus === 'success' ? 'text-green-700 dark:text-green-300' :
                  testStatus === 'failed' ? 'text-red-700 dark:text-red-300' :
                    'text-gray-500 dark:text-gray-400'
              }>
                {testStatus === 'testing' ? 'Testing connection...' : testMessage}
              </p>
            </div>
          )}

          <div className="mt-6 flex justify-between items-center">
            <button
              type="button"
              onClick={handleTestConnection}
              disabled={testStatus === 'testing' || hasErrors}
              className="px-4 py-2 text-sm font-medium text-primary-700 bg-primary-100 dark:bg-primary-900/50 dark:text-primary-300 rounded-lg hover:bg-primary-200 dark:hover:bg-primary-900 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Test Connection
            </button>
            <div className="flex space-x-3">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">Cancel</button>
              <button type="submit" disabled={hasErrors} className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-primary-400/50 disabled:cursor-not-allowed">Save Configuration</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
