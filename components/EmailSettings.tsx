import React, { useState, useEffect } from 'react';
import { useUser } from '../contexts/UserContext';
import { MailIcon, CheckIcon, XCircleIcon, CogIcon } from './icons';

export const EmailSettings: React.FC = () => {
    const { currentUser } = useUser();
    const [config, setConfig] = useState({
        smtpHost: '',
        smtpPort: 587,
        smtpUser: '',
        smtpPassword: '',
        fromEmail: '',
        fromName: '',
        useTLS: true
    });
    const [preferences, setPreferences] = useState({
        emailVerification: true,
        alertNotifications: true,
        reportDelivery: true,
        weeklyDigest: false,
        criticalAlertsOnly: false,
        recipients: [] as string[]
    });
    const [newRecipient, setNewRecipient] = useState('');
    const [testEmail, setTestEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
    const [configLoaded, setConfigLoaded] = useState(false);

    useEffect(() => {
        loadConfig();
        loadPreferences();
    }, [currentUser]);

    const loadConfig = async () => {
        if (!currentUser) return;
        try {
            const response = await fetch(`/api/tenants/${currentUser.tenantId}/email/config`);
            const data = await response.json();
            if (data.success && data.config) {
                setConfig({ ...config, ...data.config, smtpPassword: '' });
                setConfigLoaded(true);
            }
        } catch (error) {
            console.error('Failed to load config:', error);
        }
    };

    const loadPreferences = async () => {
        if (!currentUser) return;
        try {
            const response = await fetch(`http://localhost:5001/api/tenants/${currentUser.tenantId}/email/preferences`);
            const data = await response.json();
            if (data.success && data.preferences) {
                setPreferences(data.preferences);
            }
        } catch (error) {
            console.error('Failed to load preferences:', error);
        }
    };

    const handleSaveConfig = async () => {
        if (!currentUser) return;
        setLoading(true);
        setMessage(null);
        try {
            const response = await fetch(`http://localhost:5001/api/tenants/${currentUser.tenantId}/email/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const data = await response.json();
            setMessage({
                type: data.success ? 'success' : 'error',
                text: data.message || (data.success ? 'Configuration saved successfully' : 'Failed to save configuration')
            });
            if (data.success) {
                setConfigLoaded(true);
            }
        } catch (error) {
            setMessage({ type: 'error', text: 'Failed to save configuration' });
        }
        setLoading(false);
    };

    const handleTestEmail = async () => {
        if (!currentUser || !testEmail) return;
        setLoading(true);
        setMessage(null);
        try {
            const response = await fetch(`http://localhost:5001/api/tenants/${currentUser.tenantId}/email/test`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ testEmail })
            });
            const data = await response.json();
            setMessage({
                type: data.success ? 'success' : 'error',
                text: data.message || (data.success ? 'Test email sent successfully!' : 'Failed to send test email')
            });
        } catch (error) {
            setMessage({ type: 'error', text: 'Test failed' });
        }
        setLoading(false);
    };

    const handleSavePreferences = async () => {
        if (!currentUser) return;
        setLoading(true);
        setMessage(null);
        try {
            const response = await fetch(`http://localhost:5001/api/tenants/${currentUser.tenantId}/email/preferences`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(preferences)
            });
            const data = await response.json();
            setMessage({
                type: data.success ? 'success' : 'error',
                text: data.message || (data.success ? 'Preferences saved successfully' : 'Failed to save preferences')
            });
        } catch (error) {
            setMessage({ type: 'error', text: 'Failed to save preferences' });
        }
        setLoading(false);
    };

    const addRecipient = () => {
        if (newRecipient && !preferences.recipients.includes(newRecipient)) {
            setPreferences({ ...preferences, recipients: [...preferences.recipients, newRecipient] });
            setNewRecipient('');
        }
    };

    const removeRecipient = (email: string) => {
        setPreferences({ ...preferences, recipients: preferences.recipients.filter(r => r !== email) });
    };

    return (
        <div className="space-y-6">
            <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center">
                    <MailIcon className="mr-2" size={28} />
                    Email Notification Settings
                </h2>
                <p className="text-gray-600 dark:text-gray-400 mt-1">Configure SMTP settings and notification preferences for your tenant</p>
            </div>

            {message && (
                <div className={`p-4 rounded-lg flex items-center ${message.type === 'success' ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200' : 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200'}`}>
                    {message.type === 'success' ? <CheckIcon className="mr-2" size={20} /> : <XCircleIcon className="mr-2" size={20} />}
                    {message.text}
                </div>
            )}

            {/* SMTP Configuration */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 space-y-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">SMTP Configuration</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">Configure your email server settings. Supports Gmail, Outlook, SendGrid, AWS SES, and custom SMTP servers.</p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SMTP Host</label>
                        <input
                            type="text"
                            value={config.smtpHost}
                            onChange={(e) => setConfig({ ...config, smtpHost: e.target.value })}
                            placeholder="smtp.gmail.com"
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SMTP Port</label>
                        <input
                            type="number"
                            value={config.smtpPort}
                            onChange={(e) => setConfig({ ...config, smtpPort: parseInt(e.target.value) || 587 })}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                        />
                    </div>
                </div>

                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Username / Email</label>
                    <input
                        type="text"
                        value={config.smtpUser}
                        onChange={(e) => setConfig({ ...config, smtpUser: e.target.value })}
                        placeholder="notifications@company.com"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                    />
                </div>

                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password / App Password</label>
                    <input
                        type="password"
                        value={config.smtpPassword}
                        onChange={(e) => setConfig({ ...config, smtpPassword: e.target.value })}
                        placeholder={configLoaded ? "••••••••" : "Enter password"}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">For Gmail, use an App Password. Leave blank to keep existing password.</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">From Email</label>
                        <input
                            type="email"
                            value={config.fromEmail}
                            onChange={(e) => setConfig({ ...config, fromEmail: e.target.value })}
                            placeholder="noreply@company.com"
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">From Name</label>
                        <input
                            type="text"
                            value={config.fromName}
                            onChange={(e) => setConfig({ ...config, fromName: e.target.value })}
                            placeholder="Company Security Team"
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                        />
                    </div>
                </div>

                <div className="flex items-center">
                    <input
                        type="checkbox"
                        checked={config.useTLS}
                        onChange={(e) => setConfig({ ...config, useTLS: e.target.checked })}
                        className="mr-2 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                    />
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Use TLS (recommended for port 587)</label>
                </div>

                <div className="flex gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button
                        onClick={handleSaveConfig}
                        disabled={loading}
                        className="px-6 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                    >
                        {loading ? <CogIcon className="animate-spin mr-2" size={16} /> : null}
                        Save Configuration
                    </button>
                </div>
            </div>

            {/* Test Email */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 space-y-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Test Configuration</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">Send a test email to verify your SMTP settings are working correctly.</p>
                <div className="flex gap-4">
                    <input
                        type="email"
                        value={testEmail}
                        onChange={(e) => setTestEmail(e.target.value)}
                        placeholder="test@example.com"
                        className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500"
                    />
                    <button
                        onClick={handleTestEmail}
                        disabled={loading || !testEmail}
                        className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                    >
                        {loading ? <CogIcon className="animate-spin mr-2" size={16} /> : <MailIcon className="mr-2" size={16} />}
                        Send Test Email
                    </button>
                </div>
            </div>

            {/* Notification Preferences */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 space-y-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Notification Preferences</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">Choose which types of notifications to receive via email.</p>

                <div className="space-y-3">
                    <div className="flex items-center">
                        <input
                            type="checkbox"
                            checked={preferences.alertNotifications}
                            onChange={(e) => setPreferences({ ...preferences, alertNotifications: e.target.checked })}
                            className="mr-3 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                        />
                        <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Security Alert Notifications</label>
                            <p className="text-xs text-gray-500 dark:text-gray-400">Receive emails when security alerts are detected</p>
                        </div>
                    </div>

                    <div className="flex items-center">
                        <input
                            type="checkbox"
                            checked={preferences.reportDelivery}
                            onChange={(e) => setPreferences({ ...preferences, reportDelivery: e.target.checked })}
                            className="mr-3 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                        />
                        <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Report Delivery</label>
                            <p className="text-xs text-gray-500 dark:text-gray-400">Receive scheduled reports via email</p>
                        </div>
                    </div>

                    <div className="flex items-center">
                        <input
                            type="checkbox"
                            checked={preferences.weeklyDigest}
                            onChange={(e) => setPreferences({ ...preferences, weeklyDigest: e.target.checked })}
                            className="mr-3 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                        />
                        <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Weekly Digest</label>
                            <p className="text-xs text-gray-500 dark:text-gray-400">Receive a weekly summary of platform activity</p>
                        </div>
                    </div>

                    <div className="flex items-center">
                        <input
                            type="checkbox"
                            checked={preferences.criticalAlertsOnly}
                            onChange={(e) => setPreferences({ ...preferences, criticalAlertsOnly: e.target.checked })}
                            className="mr-3 h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                        />
                        <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Critical Alerts Only</label>
                            <p className="text-xs text-gray-500 dark:text-gray-400">Only receive notifications for critical severity alerts</p>
                        </div>
                    </div>
                </div>

                <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Notification Recipients</label>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">Add email addresses to receive notifications</p>

                    <div className="space-y-2">
                        {preferences.recipients.map((email, index) => (
                            <div key={index} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700 px-3 py-2 rounded-md">
                                <span className="text-sm text-gray-700 dark:text-gray-300">{email}</span>
                                <button
                                    onClick={() => removeRecipient(email)}
                                    className="text-red-600 hover:text-red-700 text-sm font-medium"
                                >
                                    Remove
                                </button>
                            </div>
                        ))}
                    </div>

                    <div className="flex gap-2 mt-3">
                        <input
                            type="email"
                            value={newRecipient}
                            onChange={(e) => setNewRecipient(e.target.value)}
                            onKeyPress={(e) => e.key === 'Enter' && addRecipient()}
                            placeholder="email@example.com"
                            className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-primary-500"
                        />
                        <button
                            onClick={addRecipient}
                            className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 text-sm"
                        >
                            Add
                        </button>
                    </div>
                </div>

                <div className="flex gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button
                        onClick={handleSavePreferences}
                        disabled={loading}
                        className="px-6 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                    >
                        {loading ? <CogIcon className="animate-spin mr-2" size={16} /> : null}
                        Save Preferences
                    </button>
                </div>
            </div>
        </div>
    );
};
