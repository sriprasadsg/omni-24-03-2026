import React, { useState, useEffect } from 'react';
import { authFetch } from '../services/apiService';

// 88.1 stage 1: this screen shows only what real sensor records say. Sensor setup and the alert lists arrive
// with stage 3; until then no tenant can have a sensor, and the screen says so. A failed or malformed
// response is an error, never "no sensor" and never "live".

interface Sensor {
  sensorId: string;
  name: string | null;
  state: string;
  reason: string | null;
  lastStatsAt: string | null;
  retiredAt: string | null;
}

const STATE_LABELS: Record<string, string> = {
  awaiting_first_report: 'Awaiting first report',
  live: 'Live',
  degraded: 'Degraded',
  silent: 'Silent',
  removed: 'Removed',
};

const REASON_LABELS: Record<string, string> = {
  no_packet_growth: 'sees no traffic',
  dropping_packets: 'dropping packets',
};

function when(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'never';
}

export default function NDRDashboard() {
  const [sensors, setSensors] = useState<Sensor[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    setFailed(false);
    try {
      const res = await authFetch('/api/ndr/summary');
      const body = res.ok ? await res.json() : null;
      if (!body || !Array.isArray(body.sensors)) throw new Error('no sensor list in the response');
      setSensors(body.sensors);
    } catch {
      setSensors(null);
      setFailed(true);
    }
  }

  return (
    <div className="p-6 bg-transparent dark:bg-gray-900 min-h-screen text-gray-900 dark:text-white">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Network Detection & Response</h1>
        <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">What your network sensors report. Nothing on this screen is simulated.</p>
      </div>

      {failed && (
        <div role="alert" className="flex items-center gap-3 bg-red-100 dark:bg-red-900/20 border border-red-200 dark:border-red-700/50 rounded-xl p-4 text-sm text-red-700 dark:text-red-300">
          <span>Couldn't load sensor status. This screen can't say whether a sensor is watching.</span>
          <button onClick={load} className="ml-auto underline hover:no-underline">Retry</button>
        </div>
      )}

      {!failed && sensors === null && (
        <p className="text-sm text-gray-600 dark:text-gray-400">Loading sensor status…</p>
      )}

      {sensors !== null && sensors.length === 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold">No network sensor is connected</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
            This platform is not watching traffic on your network. Sensor setup is not available yet.
          </p>
        </div>
      )}

      {sensors !== null && sensors.length > 0 && (
        <ul className="space-y-3">
          {sensors.map(sensor => (
            <li key={sensor.sensorId} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <p className="font-semibold">{sensor.name || sensor.sensorId}</p>
              <p className="text-sm mt-1">
                {STATE_LABELS[sensor.state] || sensor.state}
                {sensor.reason ? `: ${REASON_LABELS[sensor.reason] || sensor.reason}` : ''}
              </p>
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                {sensor.state === 'removed' ? `Removed ${when(sensor.retiredAt)}` : `Last report: ${when(sensor.lastStatsAt)}`}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
