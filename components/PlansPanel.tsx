import React, { useEffect, useState } from 'react';
import { Modal } from './Modal';
import { Plan, PlanChanges, PlanKey, fetchPlans, savePlan } from '../services/plansApi';
import { PartnerScreenPicker } from './PartnerScreenPicker';
import { ErrorBlock } from './PartnerCustomerModals';
import featureSwitches from '../shared/tenant-feature-switches.json';

/**
 * Phase 88 (LIC-07, D-14, D-17, D-28): the Super Admin's plan table, opened from Tenant Management.
 * Seats reach tenants on the plan at once; screens limit only what can be ticked from now on; trial days
 * apply to trials that start afterwards. Custom is set per tenant by contract, so it is read-only here.
 * The server enforces every bound; this screen only shapes the request and reports the answer.
 */
const groups: { name: string; features: { permission: string; label: string }[] }[] = featureSwitches.groups;
const allScreens = groups.flatMap(g => g.features.map(f => f.permission));
const MAX_SEATS = 1_000_000;

const INPUT = 'w-28 min-h-10 px-3 text-sm bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md dark:text-white';
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

const SECONDARY_BUTTON = 'min-h-10 px-4 text-sm font-semibold text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none';
const EFFECT = 'mt-1 text-xs text-gray-500 dark:text-gray-400';

const screensOf = (plan: Plan): Set<string> => new Set(plan.screens === 'all' ? allScreens : plan.screens);
const sameSet = (a: Set<string>, b: Set<string>) => a.size === b.size && [...a].every(x => b.has(x));

interface Status { kind: 'ok' | 'error'; text: string }

const PlanSection: React.FC<{ plan: Plan; onSaved: (plan: Plan) => void }> = ({ plan, onSaved }) => {
  const isFree = plan.key === 'Free';
  const [seats, setSeats] = useState(String(plan.seats ?? ''));
  const [trialDays, setTrialDays] = useState(String(plan.trialDays ?? ''));
  const [screens, setScreens] = useState<Set<string>>(() => screensOf(plan));
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  const reset = (p: Plan) => { setSeats(String(p.seats ?? '')); setTrialDays(String(p.trialDays ?? '')); setScreens(screensOf(p)); };
  const seatsChanged = seats !== String(plan.seats ?? '');
  const daysChanged = isFree && trialDays !== String(plan.trialDays ?? '');
  const screensChanged = !sameSet(screens, screensOf(plan));
  const dirty = seatsChanged || daysChanged || screensChanged;

  const save = async () => {
    const changes: PlanChanges = {};
    if (seatsChanged) {
      if (!/^\d+$/.test(seats.trim()) || Number(seats) > MAX_SEATS) {
        setStatus({ kind: 'error', text: 'Seats must be a whole number from 0 to 1,000,000.' });
        return;
      }
      changes.seats = Number(seats);
    }
    if (daysChanged) {
      if (!/^\d+$/.test(trialDays.trim()) || Number(trialDays) < 1 || Number(trialDays) > 365) {
        setStatus({ kind: 'error', text: 'Trial days must be a whole number from 1 to 365.' });
        return;
      }
      changes.trialDays = Number(trialDays);
    }
    if (screensChanged) changes.screens = allScreens.filter(s => screens.has(s));
    setSaving(true);
    setStatus(null);
    try {
      const result = await savePlan(plan.key as PlanKey, changes);
      reset(result.plan);
      onSaved(result.plan);
      setStatus({ kind: 'ok', text: `Saved. ${plural(result.tenantsUpdated, 'tenant')} updated.` });
    } catch (e) {
      setStatus({ kind: 'error', text: e instanceof Error ? e.message : 'Could not save the plan.' });
    } finally {
      setSaving(false);
    }
  };

  const seatsEffectId = `${plan.key}-seats-effect`;
  const daysEffectId = `${plan.key}-days-effect`;

  return (
    <section aria-label={`${plan.key} plan`} className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{plan.key}</h3>
        <span className="text-xs text-gray-500 dark:text-gray-400">{plural(plan.tenantCount, 'tenant')}</span>
      </div>
      {plan.key === 'Custom' ? (
        <>
          <p className="text-sm text-gray-600 dark:text-gray-300">Set per tenant by contract</p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Choose the seats and screens for each Custom tenant in Manage Tenant.</p>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-start gap-4 mb-3">
            <div className="text-sm text-gray-700 dark:text-gray-300">
              <label>
                Seats
                <input type="number" inputMode="numeric" min={0} max={MAX_SEATS} step={1} value={seats} aria-label={`${plan.key} seats`}
                  disabled={saving} aria-describedby={seatsChanged ? seatsEffectId : undefined}
                  onChange={e => setSeats(e.target.value)} className={`${INPUT} block mt-1`} />
              </label>
            </div>
            {isFree && (
              <div className="text-sm text-gray-700 dark:text-gray-300">
                <label>
                  Trial days
                  <input type="number" inputMode="numeric" min={1} max={365} step={1} value={trialDays} aria-label="Free trial days"
                    disabled={saving} aria-describedby={daysChanged ? daysEffectId : undefined}
                    onChange={e => setTrialDays(e.target.value)} className={`${INPUT} block mt-1`} />
                </label>
              </div>
            )}
          </div>
          {seatsChanged && (
            <p id={seatsEffectId} aria-live="polite" className={`mb-3 ${EFFECT}`}>
              {`Applies at once to every tenant on ${plan.key} that has no seat override (${plan.tenantCount} on this plan). Running agents are never cut off; computers over the new limit wait for approval.`}
            </p>
          )}
          {daysChanged && (
            <p id={daysEffectId} aria-live="polite" className={`mb-3 ${EFFECT}`}>Applies to trials that start afterwards.</p>
          )}
          <details className="mb-3">
            <summary className="cursor-pointer text-sm font-semibold text-gray-700 dark:text-gray-200">
              Screens ({screens.size} of {allScreens.length})
            </summary>
            <div className="mt-2 max-h-72 overflow-y-auto">
              <PartnerScreenPicker mode="ceiling" value={[...screens]} disabled={saving}
                onChange={next => setScreens(new Set(next))} />
            </div>
          </details>
          {screensChanged && (
            <p aria-live="polite" className={`mb-3 ${EFFECT}`}>Only limits what can be ticked from now on; screens already on stay on.</p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={save} disabled={!dirty || saving}
              className="min-h-10 px-4 text-sm font-semibold text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50">
              {saving ? 'Saving...' : `Save ${plan.key} plan`}
            </button>
            {status && (
              <p role={status.kind === 'error' ? 'alert' : 'status'}
                className={`text-sm ${status.kind === 'error' ? 'text-red-600 dark:text-red-400' : 'text-green-700 dark:text-green-400'}`}>
                {status.text}
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
};

export const PlansPanel: React.FC<{ isOpen: boolean; onClose: () => void }> = ({ isOpen, onClose }) => {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!isOpen) return;
    let live = true;
    setPlans(null);
    setFailed(false);
    fetchPlans()
      .then(p => { if (live) setPlans(p); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [isOpen, attempt]);

  const replace = (updated: Plan) => setPlans(prev => prev && prev.map(p => (p.key === updated.key ? updated : p)));
  const retry = <button type="button" onClick={() => setAttempt(n => n + 1)} className={SECONDARY_BUTTON}>Try again</button>;

  const footer = <button type="button" onClick={onClose} className={SECONDARY_BUTTON}>Close</button>;

  // closeOnBackdrop is off: a stray click outside must not throw away unsaved plan edits.
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Plans" size="4xl" footer={footer} closeOnBackdrop={false}>
      <div className="space-y-4">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Seat changes apply at once to every tenant on the plan without an override. Screen changes only limit what can be
          ticked from now on. Trial-day changes apply to trials that start afterwards.
        </p>
        {failed && (
          <div className="space-y-2">
            <ErrorBlock>Couldn't load the plans. Check your connection and try again.</ErrorBlock>
            {retry}
          </div>
        )}
        {!plans && !failed && <p className="text-sm text-gray-500 dark:text-gray-400" aria-busy="true">Loading plans...</p>}
        {plans && plans.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No plans were found. Try again, and if this stays empty ask whoever runs the platform to check the plan migration.
            </p>
            {retry}
          </div>
        )}
        {plans?.map(plan => <PlanSection key={plan.key} plan={plan} onSaved={replace} />)}
      </div>
    </Modal>
  );
};
