import React, { useId } from 'react';
import featureSwitches from '../shared/tenant-feature-switches.json';

/**
 * Phase 87 (PART-06, D-10, D-19): the screen checklist shared by the ceiling form (Super Admin), Create
 * customer and Choose screens (partner). Groups and labels come from the same list Manage Tenant uses
 * (shared/tenant-feature-switches.json), with the same parent rule: ticking a screen ticks the screen it
 * needs, unticking a screen unticks the screens that need it.
 *
 * In `customer` mode the picker offers only what is inside the partner's ceiling. A screen the customer
 * already holds outside it is "kept": shown on and locked, because a partner may not add it again and the
 * server keeps it whatever is sent. The server (backend/partner_portal_service) is the real wall; this only
 * stops the UI from offering what it would refuse. Nothing but switch names is shown or sent.
 *
 * Phase 88 (LIC-04, D-30; 88-UI-SPEC S11): in `customer` mode `planScreens` (the customer's plan, as the features
 * view reports it; `all` or absent means no limit) narrows what is tickable further. A screen inside the
 * partner's ceiling but outside the plan is shown greyed and described by one shared visible note, not a title
 * per row; one the customer already holds outside the plan is kept (on and locked), like any kept screen.
 */

type FeatureSwitch = { permission: string; label: string; parent?: string };
type SwitchGroup = { name: string; features: FeatureSwitch[] };

const GROUPS: SwitchGroup[] = featureSwitches.groups as SwitchGroup[];
const BY_PERMISSION = new Map<string, FeatureSwitch>(GROUPS.flatMap(g => g.features).map(f => [f.permission, f]));
const CHILDREN = new Map<string, string[]>();
for (const feature of BY_PERMISSION.values()) {
  if (feature.parent) CHILDREN.set(feature.parent, [...(CHILDREN.get(feature.parent) ?? []), feature.permission]);
}

/** Every customer starts with the Overview screen (backend tenant_features.START_FEATURES); it cannot be unticked. */
const ALWAYS_INCLUDED = 'screen:dashboard';
/** Switches in the checklist that a partner or Super Admin can tick, i.e. all but the always-included one. */
const TICKABLE_TOTAL = BY_PERMISSION.size - (BY_PERMISSION.has(ALWAYS_INCLUDED) ? 1 : 0);

const EMPTY_CEILING_MESSAGE =
  "Your platform administrator hasn't made any screens available to sell yet. Ask them to set your screen list.";
const KEPT_HINT = "Kept from before. You can't add it again.";

const descendantsOf = (permission: string): string[] =>
  (CHILDREN.get(permission) ?? []).flatMap(child => [child, ...descendantsOf(child)]);

/** Parents first, the nearest last: the screens this one needs. */
const ancestorsOf = (permission: string): string[] => {
  const parent = BY_PERMISSION.get(permission)?.parent;
  return parent && BY_PERMISSION.has(parent) ? [...ancestorsOf(parent), parent] : [];
};

const TEXT_BUTTON =
  'min-h-8 px-2 text-sm font-semibold text-gray-900 dark:text-white underline underline-offset-2 disabled:opacity-60 disabled:no-underline';

export interface PartnerScreenPickerProps {
  /** `ceiling`: the Super Admin sets what a partner may sell. `customer`: a partner picks within that ceiling. */
  mode: 'ceiling' | 'customer';
  /** The partner's ceiling (customer mode). `all` or `unrestricted` offers every switch. */
  ceiling?: string[];
  unrestricted?: boolean;
  /** The ticked switches. Entries the picker does not show (start screens, unknown names) pass through untouched. */
  value: string[];
  /** Screens the customer holds outside the ceiling (D-19), as the server reports them. */
  kept?: string[];
  /** Phase 88: the screens the customer's plan covers (customer mode); `all` or undefined means no plan limit. */
  planScreens?: string[];
  /** Phase 88: the plan's name, used in the shared note only. */
  planName?: string;
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

export const PartnerScreenPicker: React.FC<PartnerScreenPickerProps> = ({
  mode, ceiling, unrestricted, value, kept, planScreens, planName, onChange, disabled,
}) => {
  const uid = useId();
  const selected = new Set(value);
  const ceilingSet = new Set(ceiling ?? []);
  const everything = mode === 'ceiling' || !!unrestricted || ceilingSet.has('all');
  const offerable = (permission: string) => everything || ceilingSet.has(permission);
  const planSet = mode === 'customer' && planScreens && !planScreens.includes('all') ? new Set(planScreens) : null;
  const inPlan = (permission: string) => !planSet || planSet.has(permission);
  /** Inside the partner's ceiling and the customer's plan. */
  const tickable = (permission: string) => offerable(permission) && inPlan(permission);

  // D-19: held but not sellable = kept. The caller's list is trusted, and so is the evidence in `value`.
  const keptSet = new Set<string>();
  if (mode === 'customer') {
    for (const permission of [...(kept ?? []), ...value]) {
      if (BY_PERMISSION.has(permission) && permission !== ALWAYS_INCLUDED && !tickable(permission)) keptSet.add(permission);
    }
  }
  const holdsKeptChild = (permission: string) => descendantsOf(permission).some(d => keptSet.has(d));

  type Lock = 'always' | 'kept' | 'needed' | null;
  const lockOf = (permission: string): Lock => {
    if (permission === ALWAYS_INCLUDED) return 'always';
    if (keptSet.has(permission)) return 'kept';
    return holdsKeptChild(permission) ? 'needed' : null;
  };
  const isChecked = (permission: string) => selected.has(permission) || lockOf(permission) !== null;

  /** The screen it needs is on already, or can be switched on (and so on up the chain). */
  const parentReady = (permission: string): boolean => {
    const parent = BY_PERMISSION.get(permission)?.parent;
    if (!parent || !BY_PERMISSION.has(parent)) return true;
    return isChecked(parent) || (tickable(parent) && parentReady(parent));
  };
  const canToggle = (permission: string) =>
    !disabled && lockOf(permission) === null && tickable(permission) && (isChecked(permission) || parentReady(permission));
  const isVisible = (permission: string) =>
    mode === 'ceiling' || offerable(permission) || keptSet.has(permission) || lockOf(permission) !== null;

  const visibleGroups = GROUPS
    .map(group => ({ ...group, features: group.features.filter(f => isVisible(f.permission)) }))
    .filter(group => group.features.length > 0);
  const visibleCount = visibleGroups.reduce((sum, g) => sum + g.features.filter(f => f.permission !== ALWAYS_INCLUDED).length, 0);

  if (mode === 'customer' && visibleCount === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">{EMPTY_CEILING_MESSAGE}</p>;
  }

  const rows = visibleGroups.flatMap(g => g.features).map(f => f.permission);
  const tickedCount = rows.filter(p => p !== ALWAYS_INCLUDED && isChecked(p)).length;
  const countText = mode === 'ceiling'
    ? `${tickedCount} of ${TICKABLE_TOTAL} selected`
    : `${tickedCount} ${tickedCount === 1 ? 'screen' : 'screens'} selected`;

  const toggle = (permission: string) => {
    if (!canToggle(permission)) return;
    if (isChecked(permission)) {
      const removed = new Set([permission, ...descendantsOf(permission)]);
      onChange(value.filter(p => !removed.has(p)));
      return;
    }
    const added = [...ancestorsOf(permission), permission].filter(p => !selected.has(p));
    onChange([...value, ...added]);
  };
  const selectAll = () => {
    const added = rows.filter(p => canToggle(p) && !isChecked(p));
    onChange([...value, ...[...new Set(added.flatMap(p => [...ancestorsOf(p), p]))].filter(p => !selected.has(p))]);
  };
  const clearAll = () => {
    const removed = new Set(rows.filter(p => canToggle(p) && isChecked(p)).flatMap(p => [p, ...descendantsOf(p)]));
    onChange(value.filter(p => !removed.has(p)));
  };
  const planNoteId = `${uid}-plan-note`;
  /** Offered by the partner but blocked by the plan, and not held: greyed, pointing at the shared note. */
  const greyedByPlan = (permission: string) => offerable(permission) && !inPlan(permission) && lockOf(permission) === null && !isChecked(permission);
  const anyGreyed = rows.some(greyedByPlan);
  const anyToTick = rows.some(p => canToggle(p) && !isChecked(p));
  const anyToClear = rows.some(p => canToggle(p) && isChecked(p));

  const hintFor = (permission: string): string | null => {
    const lock = lockOf(permission);
    if (lock === 'always') return 'Always included';
    if (lock === 'kept') return KEPT_HINT;
    if (lock === 'needed') return 'Needed by a screen kept from before.';
    if (!isChecked(permission) && tickable(permission) && !parentReady(permission)) {
      const parent = BY_PERMISSION.get(permission)?.parent;
      return `Needs ${BY_PERMISSION.get(parent ?? '')?.label ?? parent}.`;
    }
    return null;
  };

  const renderRow = (feature: FeatureSwitch, groupFeatures: FeatureSwitch[]): React.ReactNode => {
    const { permission, label } = feature;
    const hint = hintFor(permission);
    const hintId = `${uid}-${permission}-hint`;
    const children = groupFeatures.filter(f => f.parent === permission);
    return (
      <div key={permission} className={children.length > 0 ? 'sm:col-span-2 space-y-1' : undefined}>
        <label className="flex items-center gap-3 min-h-8">
          <input
            type="checkbox"
            checked={isChecked(permission)}
            disabled={!canToggle(permission)}
            onChange={() => toggle(permission)}
            aria-describedby={hint ? hintId : greyedByPlan(permission) ? planNoteId : undefined}
            className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
        </label>
        {hint && <p id={hintId} className="ml-7 text-xs text-gray-500 dark:text-gray-400">{hint}</p>}
        {children.length > 0 && (
          <div className="ml-6 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
            {children.map(child => renderRow(child, groupFeatures))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <p className="text-sm text-gray-600 dark:text-gray-300" aria-live="polite">{countText}</p>
        <button type="button" className={TEXT_BUTTON} onClick={selectAll} disabled={disabled || !anyToTick}>
          Select all screens
        </button>
        <button type="button" className={TEXT_BUTTON} onClick={clearAll} disabled={disabled || !anyToClear}>
          Clear all screens
        </button>
      </div>
      {anyGreyed && (
        <p id={planNoteId} className="text-xs text-gray-500 dark:text-gray-400">
          {`Greyed-out screens are not in this customer's ${planName ? `${planName} ` : ''}plan.`}
        </p>
      )}
      {visibleGroups.map(group => {
        const present = new Set(group.features.map(f => f.permission));
        // A switch sits under its parent when that parent is in the same group; otherwise it stands alone.
        const top = group.features.filter(f => !f.parent || !present.has(f.parent));
        return (
          <fieldset key={group.name} className="space-y-1">
            <legend className="mb-1 text-sm font-semibold text-gray-900 dark:text-white">{group.name}</legend>
            <div className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
              {top.map(feature => renderRow(feature, group.features))}
            </div>
          </fieldset>
        );
      })}
    </div>
  );
};
