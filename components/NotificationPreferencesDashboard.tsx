import React, { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/apiService';

type Channel = 'email' | 'slack' | 'msteams';
type EventKey =
  | 'ticket.created'
  | 'ticket.commented'
  | 'ticket.escalated'
  | 'ticket.status_changed'
  | 'ticket.sla_breached';

interface Preferences {
  channels: Record<Channel, boolean>;
  events: Record<EventKey, Record<Channel, boolean>>;
}

const CHANNELS: { key: Channel; label: string }[] = [
  { key: 'email', label: 'Email' },
  { key: 'slack', label: 'Slack' },
  { key: 'msteams', label: 'MS Teams' },
];

const EVENT_KEYS: EventKey[] = [
  'ticket.created',
  'ticket.commented',
  'ticket.escalated',
  'ticket.status_changed',
  'ticket.sla_breached',
];

const defaultPrefs = (): Preferences => ({
  channels: { email: true, slack: false, msteams: false },
  events: Object.fromEntries(
    EVENT_KEYS.map(ev => [ev, { email: true, slack: false, msteams: false }])
  ) as Record<EventKey, Record<Channel, boolean>>,
});

const NotificationPreferencesDashboard: React.FC = () => {
  const [prefs, setPrefs] = useState<Preferences>(defaultPrefs());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  const showToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await authFetch('/api/users/me/notification-preferences');
      if (res.status === 404) {
        setPrefs(defaultPrefs());
      } else if (res.ok) {
        const data = await res.json();
        setPrefs(data);
      }
    } catch {
      setPrefs(defaultPrefs());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleChannel = (ch: Channel) => {
    setPrefs(p => ({ ...p, channels: { ...p.channels, [ch]: !p.channels[ch] } }));
  };

  const toggleEventChannel = (ev: EventKey, ch: Channel) => {
    setPrefs(p => ({
      ...p,
      events: {
        ...p.events,
        [ev]: { ...p.events[ev], [ch]: !p.events[ev][ch] },
      },
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await authFetch('/api/users/me/notification-preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prefs),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('Preferences saved successfully', true);
    } catch (e: any) {
      showToast(`Failed to save: ${e.message}`, false);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-gray-900 min-h-screen text-white p-6 flex items-center justify-center">
        <p className="text-gray-400">Loading preferences…</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 min-h-screen text-white p-6">
      <div className="max-w-2xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Notification Preferences</h1>
          <p className="text-gray-400 text-sm mt-1">Configure how and when you receive notifications</p>
        </div>

        {/* Channel toggles */}
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 mb-5">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">Channels</h2>
          <div className="space-y-3">
            {CHANNELS.map(({ key, label }) => (
              <label key={key} className="flex items-center justify-between cursor-pointer group">
                <span className="text-gray-300 group-hover:text-white transition-colors">{label}</span>
                <button
                  role="switch"
                  aria-checked={prefs.channels[key]}
                  onClick={() => toggleChannel(key)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    prefs.channels[key] ? 'bg-blue-600' : 'bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      prefs.channels[key] ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </label>
            ))}
          </div>
        </div>

        {/* Per-event preferences */}
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 mb-5">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">Event Notifications</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700">
                  <th className="text-left pb-3 text-gray-400 font-medium text-xs uppercase">Event</th>
                  {CHANNELS.map(({ key, label }) => (
                    <th key={key} className="pb-3 text-gray-400 font-medium text-xs uppercase text-center w-24">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {EVENT_KEYS.map(ev => (
                  <tr key={ev} className="border-b border-gray-700/50">
                    <td className="py-3 text-gray-300">{ev}</td>
                    {CHANNELS.map(({ key: ch }) => (
                      <td key={ch} className="py-3 text-center">
                        <input
                          type="checkbox"
                          checked={prefs.events[ev]?.[ch] ?? false}
                          onChange={() => toggleEventChannel(ev, ch)}
                          disabled={!prefs.channels[ch]}
                          className="rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed"
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-gray-500 text-xs mt-3">Disabled channels will not send any notifications regardless of per-event settings.</p>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? 'Saving…' : 'Save Preferences'}
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg text-sm font-medium z-50 transition-all ${
            toast.ok ? 'bg-green-700 text-white' : 'bg-red-700 text-white'
          }`}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
};

export default NotificationPreferencesDashboard;
