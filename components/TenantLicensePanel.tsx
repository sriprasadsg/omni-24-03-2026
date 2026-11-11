import React, { useEffect, useState } from 'react';
import { fetchLicenceView, updateLicence, LicenceView, LicenceChanges, LicenceSubLimit } from '../services/licenceApi';

interface TenantLicensePanelProps {
  tenantId: string;
}

const OS_KEYS = ['os:windows_workstation', 'os:windows_server', 'os:linux', 'os:macos'];

const dateOf = (iso: string | null) => (iso ? iso.slice(0, 10) : '');
const sameLimits = (a: LicenceSubLimit[], b: LicenceSubLimit[]) =>
  a.length === b.length && a.every((s, i) => s.key === b[i].key && s.max === b[i].max);

/**
 * Agent license editor for super admins: seat limit and reclaim window (spec C2), plus the
 * enrollment controls of spec C4: an expiry date, allowlist enforcement and sub-limits per
 * OS class or agent group. New machines that break a rule wait for approval under Agents.
 * Plan-driven (88-13): the plan's seat number beside the tenant's limit with "Use plan number" (D-09), the Free
 * trial end with an extension (D-15) and the allowed networks, read-only (D-19).
 */
export const TenantLicensePanel: React.FC<TenantLicensePanelProps> = ({ tenantId }) => {
  const [license, setLicense] = useState<LicenceView | null>(null);
  const [maxAgents, setMaxAgents] = useState('');
  const [reclaimDays, setReclaimDays] = useState('');
  const [expiresOn, setExpiresOn] = useState('');
  const [allowlistMode, setAllowlistMode] = useState<'off' | 'enforce'>('off');
  const [subLimits, setSubLimits] = useState<{ key: string; max: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [extendDays, setExtendDays] = useState('7');
  const [acting, setActing] = useState(false);

  const adopt = (l: LicenceView) => {
    setLicense(l);
    setMaxAgents(l.maxAgents === null ? '' : String(l.maxAgents));
    setReclaimDays(String(l.inactiveReclaimDays));
    setExpiresOn(dateOf(l.expiresAt));
    setAllowlistMode(l.allowlistMode || 'off');
    setSubLimits((l.subLimits || []).map(s => ({ key: s.key, max: String(s.max) })));
  };

  useEffect(() => {
    let active = true;
    setError(null);
    fetchLicenceView(tenantId)
      .then(l => { if (active) adopt(l); })
      .catch(e => active && setError(e.message));
    return () => { active = false; };
  }, [tenantId]);

  const parsedMax = Number(maxAgents);
  const parsedDays = Number(reclaimDays);
  const parsedLimits: LicenceSubLimit[] = subLimits
    .filter(s => s.key.trim())
    .map(s => ({ key: s.key.trim(), max: Number(s.max) }));
  const limitsValid = parsedLimits.every(s => Number.isInteger(s.max) && s.max >= 0);
  const valid = maxAgents.trim() !== '' && Number.isInteger(parsedMax) && parsedMax >= 0 && Number.isInteger(parsedDays)
    && parsedDays >= 1 && parsedDays <= 365 && limitsValid;
  const expiryChanged = !!license && expiresOn !== dateOf(license.expiresAt);
  const dirty = !!license && (parsedMax !== license.maxAgents || parsedDays !== license.inactiveReclaimDays
    || expiryChanged || allowlistMode !== (license.allowlistMode || 'off')
    || !sameLimits(parsedLimits, license.subLimits || []));

  const save = async () => {
    if (!license || !valid || !dirty) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const changes: LicenceChanges = {
        maxAgents: parsedMax, inactiveReclaimDays: parsedDays, allowlistMode, subLimits: parsedLimits,
      };
      if (expiryChanged) changes.expiresAt = expiresOn ? new Date(`${expiresOn}T23:59:59Z`).toISOString() : null;
      adopt(await updateLicence(tenantId, changes));
      setSaved(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const touch = () => setSaved(false);

  // "Use plan number" and "Extend" are their own PATCH; the server answers the whole licence view.
  const act = async (changes: LicenceChanges, reset: boolean) => {
    setActing(true);
    setError(null);
    setSaved(false);
    try {
      const next = await updateLicence(tenantId, changes);
      if (reset) adopt(next); else setLicense(next);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActing(false);
    }
  };
  const parsedExtend = Number(extendDays);
  const extendValid = extendDays.trim() !== '' && Number.isInteger(parsedExtend) && parsedExtend >= 1 && parsedExtend <= 365;
  const trial = license?.trial ?? null;
  const showOverride = !!license && license.seatOverride !== null && !license.partnerManaged;
  const canUsePlanNumber = showOverride && license!.plan !== 'Custom';
  const inputClass = 'w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white';
  const expired = !!license?.expiresAt && new Date(license.expiresAt) < new Date();

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4" data-testid="tenant-license-panel">
      <h3 className="text-sm font-bold text-gray-800 dark:text-white mb-1">Agent License</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Seats are tied to each machine's hardware. Agents silent longer than the reclaim window give their seat back.
        New machines that break a rule below wait for approval under Agents.
      </p>
      {license && (
        <p className="text-sm mb-3 text-gray-700 dark:text-gray-300">
          <strong>{license.seatsUsed}</strong> of <strong>{license.exempt ? 'unlimited' : license.maxAgents}</strong> seats in use
          {license.overBy > 0
            ? <span className="ml-2 text-red-600 dark:text-red-400">({license.overBy} over the limit: new installs wait for approval)</span>
            : <span className="ml-2 text-gray-500 dark:text-gray-400">({license.seatsAvailable} free)</span>}
          {expired && <span className="ml-2 text-red-600 dark:text-red-400">License expired: new installs wait for approval</span>}
        </p>
      )}
      {license && !license.exempt && (
        <div className="mb-3 rounded-md bg-gray-50 dark:bg-gray-900/40 p-3 text-sm text-gray-700 dark:text-gray-300" data-testid="license-plan-row">
          <p>{license.planSeats === null ? `Plan ${license.plan}: seats set per tenant` : `Plan ${license.plan}: ${license.planSeats} seats`}</p>
          <p>{`Limit ${license.maxAgents}${showOverride ? ' (override)' : ''}`}</p>
          {license.partnerManaged && (
            <p className="text-xs text-gray-500 dark:text-gray-400">The partner's allotment sets the seats for this customer.</p>
          )}
          {canUsePlanNumber && (
            <button type="button" disabled={acting} onClick={() => act({ clearSeatOverride: true }, true)}
                    className="mt-1 text-xs text-primary-600 dark:text-primary-400 disabled:opacity-50">Use plan number</button>
          )}
        </div>
      )}
      {license && license.plan === 'Free' && trial && (
        <div className="mb-3 rounded-md bg-gray-50 dark:bg-gray-900/40 p-3 text-sm text-gray-700 dark:text-gray-300" data-testid="license-trial-row">
          <p>
            {`Free trial ends ${dateOf(trial.endsAt)}: `}
            <strong>{trial.ended ? 'ended' : `${trial.daysLeft} ${trial.daysLeft === 1 ? 'day' : 'days'} left`}</strong>
          </p>
          <div className="mt-1 flex items-center gap-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-300 flex items-center gap-2">
              Extend trial by (days)
              <input type="number" min={1} max={365} className={`${inputClass} w-24`} value={extendDays}
                     onChange={e => setExtendDays(e.target.value)} />
            </label>
            <button type="button" disabled={!extendValid || acting} onClick={() => act({ trialExtendDays: parsedExtend }, false)}
                    className="px-2 py-1 text-xs rounded-md border border-gray-300 dark:border-gray-600 disabled:opacity-50">Extend</button>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <label className="text-xs font-medium text-gray-600 dark:text-gray-300">
          Max agents
          <input type="number" min={0} className={inputClass} value={maxAgents} disabled={!license}
                 onChange={e => { setMaxAgents(e.target.value); touch(); }} />
        </label>
        <label className="text-xs font-medium text-gray-600 dark:text-gray-300">
          Reclaim after (days offline)
          <input type="number" min={1} max={365} className={inputClass} value={reclaimDays} disabled={!license}
                 onChange={e => { setReclaimDays(e.target.value); touch(); }} />
        </label>
        <label className="text-xs font-medium text-gray-600 dark:text-gray-300">
          License expires on (empty = never)
          <input type="date" className={inputClass} value={expiresOn} disabled={!license}
                 onChange={e => { setExpiresOn(e.target.value); touch(); }} />
        </label>
        <label className="text-xs font-medium text-gray-600 dark:text-gray-300">
          Hardware allowlist
          <select className={inputClass} value={allowlistMode} disabled={!license}
                  onChange={e => { setAllowlistMode(e.target.value as 'off' | 'enforce'); touch(); }}>
            <option value="off">Off: any machine may enroll</option>
            <option value="enforce">Enforce: only listed machines enroll</option>
          </select>
        </label>
      </div>
      {license && license.seatsUsed > parsedMax && Number.isInteger(parsedMax) && (
        <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
          Below seats in use: running agents keep working, but new installs will wait for approval until seats free up.
        </p>
      )}

      <div className="mt-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">Sub-limits (within the total)</span>
          <button type="button" disabled={!license} className="text-xs text-primary-600 dark:text-primary-400"
                  onClick={() => { setSubLimits([...subLimits, { key: '', max: '1' }]); touch(); }}>+ Add sub-limit</button>
        </div>
        <datalist id={`sublimit-keys-${tenantId}`}>
          {OS_KEYS.map(k => <option key={k} value={k} />)}
          <option value="group:" />
        </datalist>
        {subLimits.map((s, i) => (
          <div key={i} className="mt-2 flex gap-2 items-center">
            <input aria-label="Sub-limit key" list={`sublimit-keys-${tenantId}`} className={inputClass} value={s.key}
                   placeholder="os:windows_server or group:<agent group id>"
                   onChange={e => { setSubLimits(subLimits.map((x, j) => j === i ? { ...x, key: e.target.value } : x)); touch(); }} />
            <input aria-label="Sub-limit max" type="number" min={0} className={`${inputClass} w-24`} value={s.max}
                   onChange={e => { setSubLimits(subLimits.map((x, j) => j === i ? { ...x, max: e.target.value } : x)); touch(); }} />
            <button type="button" aria-label="Remove sub-limit" className="text-xs text-red-600"
                    onClick={() => { setSubLimits(subLimits.filter((_, j) => j !== i)); touch(); }}>Remove</button>
          </div>
        ))}
      </div>

      {license && (
        <div className="mt-3">
          <p className="text-xs font-medium text-gray-600 dark:text-gray-300">Allowed networks</p>
          {license.allowedNetworks.length === 0
            ? <p className="text-xs text-gray-500 dark:text-gray-400">None yet: the first computer to enroll sets the network.</p>
            : <ul className="mt-1 space-y-0.5">{license.allowedNetworks.map(n => (
                <li key={n.cidr} className="text-sm text-gray-700 dark:text-gray-300">{`${n.cidr} (${n.source})`}</li>))}</ul>}
        </div>
      )}

      {error && <p className="mt-2 text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
      <div className="mt-3 flex items-center gap-3">
        <button type="button" onClick={save} disabled={!valid || !dirty || saving}
                className="px-3 py-1.5 text-sm rounded-md bg-primary-600 text-white disabled:opacity-50">
          {saving ? 'Saving…' : 'Save license'}
        </button>
        {saved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
      </div>
    </div>
  );
};
