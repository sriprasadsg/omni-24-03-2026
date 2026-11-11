import React, { useEffect, useState } from 'react';
import { fetchLicenceView, networkLabel, LicenceView } from '../services/licenceApi';

/**
 * The tenant admin's read-only licence card (D-19, D-21): plan, seats used of the limit, the days left on a
 * Free trial and the networks computers may enroll from. Nothing here edits anything: the plan, the seat
 * number and the networks are changed by the Super Admin (or the partner). Renders nothing for the platform
 * organization (exempt) or when the licence read is refused.
 */
export const TenantPlanCard: React.FC<{ tenantId: string }> = ({ tenantId }) => {
  const [view, setView] = useState<LicenceView | null>(null);

  useEffect(() => {
    let active = true;
    setView(null);
    fetchLicenceView(tenantId)
      .then(v => { if (active) setView(v); })
      .catch(() => { if (active) setView(null); });
    return () => { active = false; };
  }, [tenantId]);

  // A body that is not a licence view (a refused or malformed read) shows nothing.
  if (!view || view.exempt || typeof view.plan !== 'string' || !Array.isArray(view.allowedNetworks)) return null;

  const isFree = view.plan === 'Free';
  const trial = view.trial;
  const trialEnded = isFree && !!trial && trial.ended;
  const trialRunning = isFree && !!trial && !trial.consumed && !trial.ended;
  const days = trial?.daysLeft ?? 0;
  const mark = view.partnerManaged ? 'set by your partner' : view.seatOverride !== null ? 'override' : null;

  return (
    <section className="glass rounded-2xl p-5" data-testid="tenant-plan-card" aria-label="Your plan">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Your plan</h3>
        <span className="text-sm font-semibold text-gray-900 dark:text-white">{view.plan}</span>
      </div>
      <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
        {view.seatsUsed} of {view.maxAgents} seats used
        {mark && <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">({mark})</span>}
      </p>
      {trialRunning && (
        <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
          {days} {days === 1 ? 'day' : 'days'} left in your free trial
        </p>
      )}
      {trialEnded && (
        <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
          Your free trial has ended. New computers wait for approval; running agents and screens keep working.
        </p>
      )}
      <div className="mt-3">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400">Allowed networks</p>
        {view.allowedNetworks.length === 0 ? (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            No network learned yet: the first computer you enroll sets it.
          </p>
        ) : (
          <>
            <ul className="mt-1 space-y-1">
              {view.allowedNetworks.map(n => (
                <li key={n.cidr} className="text-sm text-gray-700 dark:text-gray-300 break-all">{`${networkLabel(n.cidr)} (${n.source})`}</li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Computers enrolling from any other network wait for approval.
            </p>
          </>
        )}
      </div>
    </section>
  );
};
