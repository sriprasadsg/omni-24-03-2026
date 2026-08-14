import React, { useState } from 'react';

const NotificationSettings: React.FC = () => {
    const [warrantyAlertsEnabled, setWarrantyAlertsEnabled] = useState(true);
    const [emailNotificationsEnabled, setEmailNotificationsEnabled] = useState(true);
    const [slackNotificationsEnabled, setSlackNotificationsEnabled] = useState(false);

    const handleSaveSettings = () => {
        // In a real application, you would send these settings to a backend API
        console.log('Saving settings:', {
            warrantyAlertsEnabled,
            emailNotificationsEnabled,
            slackNotificationsEnabled
        });
        alert('Settings saved!');
    };

    return (
        <div className="container mx-auto p-4">
            <h1 className="text-2xl font-bold mb-4">Notification Settings</h1>

            <div className="bg-white shadow overflow-hidden sm:rounded-lg mb-6">
                <div className="px-4 py-5 sm:px-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">ITAM Alerts</h3>
                </div>
                <div className="border-t border-gray-200 px-4 py-5 sm:p-6">
                    <div className="flex items-center justify-between">
                        <label htmlFor="warranty-alerts" className="flex flex-col cursor-pointer">
                            <span className="text-sm font-medium text-gray-900">Warranty Expiry Alerts</span>
                            <span className="text-sm text-gray-500">Receive notifications for expiring asset warranties.</span>
                        </label>
                        <div className="relative inline-block w-10 mr-2 align-middle select-none transition duration-200 ease-in">
                            <input
                                type="checkbox"
                                name="warranty-alerts"
                                id="warranty-alerts"
                                className="toggle-checkbox absolute block w-6 h-6 rounded-full bg-white border-4 appearance-none cursor-pointer"
                                checked={warrantyAlertsEnabled}
                                onChange={() => setWarrantyAlertsEnabled(!warrantyAlertsEnabled)}
                            />
                            <label htmlFor="warranty-alerts" className="toggle-label block overflow-hidden h-6 rounded-full bg-gray-300 cursor-pointer"></label>
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-white shadow overflow-hidden sm:rounded-lg mb-6">
                <div className="px-4 py-5 sm:px-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">General Notifications</h3>
                </div>
                <div className="border-t border-gray-200 px-4 py-5 sm:p-6 space-y-4">
                    <div className="flex items-center justify-between">
                        <label htmlFor="email-notifications" className="flex flex-col cursor-pointer">
                            <span className="text-sm font-medium text-gray-900">Email Notifications</span>
                            <span className="text-sm text-gray-500">Receive alerts via email.</span>
                        </label>
                        <div className="relative inline-block w-10 mr-2 align-middle select-none transition duration-200 ease-in">
                            <input
                                type="checkbox"
                                name="email-notifications"
                                id="email-notifications"
                                className="toggle-checkbox absolute block w-6 h-6 rounded-full bg-white border-4 appearance-none cursor-pointer"
                                checked={emailNotificationsEnabled}
                                onChange={() => setEmailNotificationsEnabled(!emailNotificationsEnabled)}
                            />
                            <label htmlFor="email-notifications" className="toggle-label block overflow-hidden h-6 rounded-full bg-gray-300 cursor-pointer"></label>
                        </div>
                    </div>
                    <div className="flex items-center justify-between">
                        <label htmlFor="slack-notifications" className="flex flex-col cursor-pointer">
                            <span className="text-sm font-medium text-gray-900">Slack Notifications</span>
                            <span className="text-sm text-gray-500">Receive alerts in your configured Slack channels.</span>
                        </label>
                        <div className="relative inline-block w-10 mr-2 align-middle select-none transition duration-200 ease-in">
                            <input
                                type="checkbox"
                                name="slack-notifications"
                                id="slack-notifications"
                                className="toggle-checkbox absolute block w-6 h-6 rounded-full bg-white border-4 appearance-none cursor-pointer"
                                checked={slackNotificationsEnabled}
                                onChange={() => setSlackNotificationsEnabled(!slackNotificationsEnabled)}
                            />
                            <label htmlFor="slack-notifications" className="toggle-label block overflow-hidden h-6 rounded-full bg-gray-300 cursor-pointer"></label>
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-6">
                <button
                    onClick={handleSaveSettings}
                    className="px-4 py-2 bg-blue-600 border border-transparent rounded-md shadow-sm text-sm font-medium text-white hover:bg-blue-700"
                >
                    Save Settings
                </button>
            </div>

            <style>{`
                .toggle-checkbox:checked {
                    right: 0;
                    border-color: #68D391;
                }
                .toggle-checkbox:checked + .toggle-label {
                    background-color: #68D391;
                }
                .toggle-label {
                    @apply bg-gray-300;
                }
                .toggle-checkbox:checked + .toggle-label {
                    @apply bg-blue-500;
                }
                .toggle-checkbox:checked {
                    @apply transform translate-x-full;
                }
            `}</style>
        </div>
    );
};

export default NotificationSettings;