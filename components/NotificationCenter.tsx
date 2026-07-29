import React, { useState, useEffect, useRef } from 'react';
import {
    BellIcon,
    XIcon,
    CheckIcon,
    TrashIcon,
    SettingsIcon,
    AlertTriangleIcon,
    InfoIcon,
    ShieldAlertIcon,
    RefreshCwIcon,
    SlackIcon,
    MailIcon,
    MessageSquareWarningIcon
} from './icons';
import {
    getNotifications,
    markNotificationRead,
    deleteNotification,
    getNotificationConfig,
    updateNotificationConfig
} from '../services/apiService';
import { useUser } from '../contexts/UserContext';

interface Notification {
    alert_id: string;
    title: string;
    message: string;
    severity: 'critical' | 'warning' | 'info';
    sent_at: string;
    read?: boolean;
    channels: Record<string, any>;
    metadata?: Record<string, any>;
}

interface NotificationConfig {
    type: string;
    enabled: boolean;
    webhook_url?: string;
    recipients?: string[];
}

const NotificationCenter: React.FC = () => {
    const { hasPermission } = useUser();
    // Notification config (Slack/email) is a tenant-settings feature — only users
    // with manage:settings may read/edit it. Gate the fetch and the gear so other
    // roles don't trigger a 403 on the config endpoint.
    const canManageSettings = hasPermission('manage:settings' as any);
    const [isOpen, setIsOpen] = useState(false);
    const [notifications, setNotifications] = useState<Notification[]>([]);
    const [configs, setConfigs] = useState<NotificationConfig[]>([]);
    const [loading, setLoading] = useState(false);
    const [showConfig, setShowConfig] = useState(false);
    const [activeTab, setActiveTab] = useState<'all' | 'unread'>('all');
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Channel config form state
    const [slackWebhook, setSlackWebhook] = useState('');
    const [slackEnabled, setSlackEnabled] = useState(false);
    const [emailEnabled, setEmailEnabled] = useState(true);
    const [configSaving, setConfigSaving] = useState(false);
    const [configMsg, setConfigMsg] = useState<{ ok: boolean; text: string } | null>(null);

    const fetchAll = async () => {
        setLoading(true);
        const [notifs, cfgs] = await Promise.all([
            getNotifications(),
            canManageSettings ? getNotificationConfig() : Promise.resolve([]),
        ]);
        setNotifications(notifs);
        setConfigs(cfgs);
        // Populate config form from loaded data
        const slackCfg = cfgs.find((c: NotificationConfig) => c.type === 'slack');
        const emailCfg = cfgs.find((c: NotificationConfig) => c.type === 'email');
        if (slackCfg) {
            setSlackEnabled(slackCfg.enabled ?? false);
            setSlackWebhook(slackCfg.webhook_url && slackCfg.webhook_url !== '***' ? slackCfg.webhook_url : '');
        }
        if (emailCfg) setEmailEnabled(emailCfg.enabled ?? true);
        setLoading(false);
    };

    const handleSaveConfig = async () => {
        setConfigSaving(true);
        setConfigMsg(null);
        try {
            await Promise.all([
                updateNotificationConfig({ type: 'slack', enabled: slackEnabled, webhook_url: slackWebhook }),
                updateNotificationConfig({ type: 'email', enabled: emailEnabled }),
            ]);
            setConfigMsg({ ok: true, text: 'Configuration saved.' });
        } catch {
            setConfigMsg({ ok: false, text: 'Failed to save. Please try again.' });
        }
        setConfigSaving(false);
    };

    useEffect(() => {
        if (isOpen) {
            fetchAll();
        }
    }, [isOpen]);

    // Background polling — keeps the unread badge fresh without opening the panel
    useEffect(() => {
        const token = sessionStorage.getItem('token');
        if (!token) return;
        const poll = async () => {
            try {
                const notifs = await getNotifications();
                if (Array.isArray(notifs)) setNotifications(notifs);
            } catch { /* ignore */ }
        };
        poll(); // initial fetch on mount
        const timer = setInterval(poll, 60_000);
        return () => clearInterval(timer);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleMarkRead = async (id: string) => {
        await markNotificationRead(id);
        setNotifications(prev => prev.map(n => n.alert_id === id ? { ...n, read: true } : n));
    };

    const handleDelete = async (id: string) => {
        await deleteNotification(id);
        setNotifications(prev => prev.filter(n => n.alert_id !== id));
    };

    const safeNotifications = Array.isArray(notifications) ? notifications : [];
    const unreadCount = safeNotifications.filter(n => !n.read).length;
    const filteredNotifications = activeTab === 'all' ? safeNotifications : safeNotifications.filter(n => !n.read);

    const getSeverityIcon = (severity: string) => {
        switch (severity) {
            case 'critical': return <ShieldAlertIcon className="text-red-500" size={18} />;
            case 'warning': return <AlertTriangleIcon className="text-yellow-500" size={18} />;
            default: return <InfoIcon className="text-blue-500" size={18} />;
        }
    };

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="relative p-2 text-gray-400 hover:text-white transition-colors rounded-full hover:bg-white/10"
            >
                <BellIcon size={20} />
                {unreadCount > 0 && (
                    <span className="absolute top-0 right-0 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white border-2 border-[#0a0a0a]">
                        {unreadCount}
                    </span>
                )}
            </button>

            {isOpen && (
                <div className="absolute right-0 mt-2 w-96 max-h-[600px] overflow-hidden bg-[#121212] border border-white/10 rounded-xl shadow-2xl z-50 flex flex-col animate-in fade-in slide-in-from-top-2 duration-200">
                    {/* Header */}
                    <div className="p-4 border-b border-white/10 flex items-center justify-between bg-white/5">
                        <h3 className="font-semibold text-white flex items-center gap-2">
                            <BellIcon size={16} />
                            Notifications
                        </h3>
                        <div className="flex items-center gap-2">
                            {canManageSettings && (
                                <button
                                    onClick={() => setShowConfig(!showConfig)}
                                    className={`p-1.5 rounded-lg transition-colors ${showConfig ? 'bg-blue-500/20 text-blue-400' : 'text-gray-400 hover:bg-white/10'}`}
                                    title="Notification Settings"
                                >
                                    <SettingsIcon size={16} />
                                </button>
                            )}
                            <button
                                onClick={fetchAll}
                                className="p-1.5 text-gray-400 hover:bg-white/10 rounded-lg transition-colors"
                                title="Refresh"
                            >
                                <RefreshCwIcon size={16} className={loading ? 'animate-spin' : ''} />
                            </button>
                        </div>
                    </div>

                    {showConfig ? (
                        <div className="p-4 overflow-y-auto space-y-4">
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-sm font-medium text-gray-300">Channel Configuration</span>
                                <button onClick={() => setShowConfig(false)} className="text-xs text-blue-400 hover:underline">Back</button>
                            </div>

                            {/* Slack Config */}
                            <div className="p-3 bg-white/5 rounded-lg border border-white/5 space-y-3">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2 text-white text-sm">
                                        <SlackIcon size={16} className="text-[#4A154B]" />
                                        Slack Webhook
                                    </div>
                                    <button
                                        role="switch"
                                        aria-checked={slackEnabled}
                                        onClick={() => setSlackEnabled(v => !v)}
                                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${slackEnabled ? 'bg-blue-600' : 'bg-gray-600'}`}
                                    >
                                        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${slackEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                                    </button>
                                </div>
                                <input
                                    type="text"
                                    value={slackWebhook}
                                    onChange={e => setSlackWebhook(e.target.value)}
                                    placeholder="https://hooks.slack.com/services/..."
                                    disabled={!slackEnabled}
                                    className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-blue-500/50 disabled:opacity-40"
                                />
                            </div>

                            {/* Email Config */}
                            <div className="p-3 bg-white/5 rounded-lg border border-white/5 space-y-2">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2 text-white text-sm">
                                        <MailIcon size={16} className="text-blue-400" />
                                        Email Alerts
                                    </div>
                                    <button
                                        role="switch"
                                        aria-checked={emailEnabled}
                                        onClick={() => setEmailEnabled(v => !v)}
                                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${emailEnabled ? 'bg-blue-600' : 'bg-gray-600'}`}
                                    >
                                        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${emailEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                                    </button>
                                </div>
                                <p className="text-[10px] text-gray-500">Configure SMTP recipients in Settings → Email Notifications</p>
                            </div>

                            {configMsg && (
                                <p className={`text-xs px-2 py-1 rounded ${configMsg.ok ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                    {configMsg.text}
                                </p>
                            )}

                            <button
                                onClick={handleSaveConfig}
                                disabled={configSaving}
                                className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors mt-4"
                            >
                                {configSaving ? 'Saving…' : 'Save Configuration'}
                            </button>
                        </div>
                    ) : (
                        <>
                            {/* Tabs */}
                            <div className="flex border-b border-white/10 px-4">
                                <button
                                    onClick={() => setActiveTab('all')}
                                    className={`py-2 px-4 text-xs font-medium border-b-2 transition-colors ${activeTab === 'all' ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-300'}`}
                                >
                                    All
                                </button>
                                <button
                                    onClick={() => setActiveTab('unread')}
                                    className={`py-2 px-4 text-xs font-medium border-b-2 transition-colors ${activeTab === 'unread' ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-500 hover:text-gray-300'}`}
                                >
                                    Unread {unreadCount > 0 && `(${unreadCount})`}
                                </button>
                            </div>

                            {/* List */}
                            <div className="overflow-y-auto flex-1 custom-scrollbar min-h-[300px]">
                                {loading ? (
                                    <div className="flex flex-col items-center justify-center h-48 text-gray-500 gap-2">
                                        <RefreshCwIcon className="animate-spin" size={24} />
                                        <span className="text-sm">Fetching alerts...</span>
                                    </div>
                                ) : filteredNotifications.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-48 text-gray-500 gap-2 opacity-50">
                                        <BellIcon size={32} />
                                        <span className="text-sm">No notifications found</span>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-white/5">
                                        {filteredNotifications.map((notif) => (
                                            <div
                                                key={notif.alert_id}
                                                className={`p-4 hover:bg-white/5 transition-colors group relative ${!notif.read ? 'bg-blue-500/5' : ''}`}
                                            >
                                                <div className="flex gap-3">
                                                    <div className="mt-1 flex-shrink-0">
                                                        {getSeverityIcon(notif.severity)}
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center justify-between mb-1">
                                                            <span className="text-sm font-semibold text-white truncate pr-8">{notif.title}</span>
                                                            <span className="text-[10px] text-gray-500 whitespace-nowrap">
                                                                {new Date(notif.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                            </span>
                                                        </div>
                                                        <p className="text-xs text-gray-400 leading-relaxed mb-2 line-clamp-2">
                                                            {notif.message}
                                                        </p>

                                                        <div className="flex items-center gap-3">
                                                            <div className="flex items-center gap-1">
                                                                {Object.keys(notif.channels).map(channel => (
                                                                    <span key={channel} className="text-[10px] text-gray-600 uppercase font-bold">{channel}</span>
                                                                ))}
                                                            </div>
                                                            {!notif.read && (
                                                                <button
                                                                    onClick={() => handleMarkRead(notif.alert_id)}
                                                                    className="text-[10px] text-blue-400 hover:underline flex items-center gap-1"
                                                                >
                                                                    <CheckIcon size={10} /> Mark read
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Action Buttons (Hover) */}
                                                <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                                                    <button
                                                        onClick={() => handleDelete(notif.alert_id)}
                                                        className="p-1.5 bg-red-500/20 text-red-400 rounded hover:bg-red-500 hover:text-white transition-all"
                                                        title="Delete"
                                                    >
                                                        <TrashIcon size={12} />
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Footer */}
                            <div className="p-3 border-t border-white/10 text-center bg-white/5">
                                <button className="text-xs text-blue-400 hover:text-blue-300 font-medium transition-colors">
                                    View All Activity
                                </button>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
};

export default NotificationCenter;
