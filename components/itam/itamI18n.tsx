import React, { createContext, useContext, useMemo } from 'react';
import type { ItamLocale } from '../../types';

// Small hand-rolled locale context for the ITAM console's own labels (Phase 65 Plan 04,
// ITAM-SET-03). Not i18next/react-i18next — see 65-04-PLAN.md Task 3's "Approach
// decision" for the full rationale (scope is the console's own labels, not
// whole-application translation; zero existing i18n convention in this repo;
// react-i18next was flagged [SUS] by 65-RESEARCH.md's package-legitimacy audit, and this
// module makes that flag moot by installing nothing). If whole-application i18n is
// scoped later, this module's useItamT call sites are a mechanical migration target.
export type { ItamLocale };

// The key set is intentionally tight — every key below is used by a real call site in
// this plan (ITAMConsole.tsx's header/TABS labels, SettingsPanel.tsx's Save/Loading text
// and the new Interface language selector). Not a speculative, whole-app dictionary.
const DICTIONARIES: Record<ItamLocale, Record<string, string>> = {
  en: {
    'tabs.catalog': 'Catalog',
    'tabs.lifecycle': 'Check-Out/In',
    'tabs.finance': 'Procurement & Finance',
    'tabs.purchaseOrders': 'Purchase Orders',
    'tabs.requests': 'Requests',
    'tabs.licenses': 'Licenses & Consumables',
    'tabs.compliance': 'Compliance',
    'tabs.software': 'Software Inventory',
    'tabs.reports': 'Reports',
    'tabs.activity': 'Activity',
    'tabs.data': 'Import / Export',
    'tabs.settings': 'Settings',
    'header.title': 'IT Asset Management Console',
    'header.subtitle':
      'Catalog, lifecycle, procurement, licenses, and compliance for every asset — agent-discovered and manually catalogued alike.',
    'settings.save': 'Save settings',
    'settings.saving': 'Saving…',
    'settings.loading': 'Loading…',
    'settings.interfaceLanguage': 'Interface language',
  },
  es: {
    'tabs.catalog': 'Catálogo',
    'tabs.lifecycle': 'Entrada/Salida',
    'tabs.finance': 'Compras y Finanzas',
    'tabs.purchaseOrders': 'Órdenes de Compra',
    'tabs.requests': 'Solicitudes',
    'tabs.licenses': 'Licencias y Consumibles',
    'tabs.compliance': 'Cumplimiento',
    'tabs.software': 'Inventario de Software',
    'tabs.reports': 'Informes',
    'tabs.activity': 'Actividad',
    'tabs.data': 'Importar / Exportar',
    'tabs.settings': 'Configuración',
    'header.title': 'Consola de Gestión de Activos de TI',
    'header.subtitle':
      'Catálogo, ciclo de vida, compras, licencias y cumplimiento para cada activo — detectado por el agente o catalogado manualmente.',
    'settings.save': 'Guardar configuración',
    'settings.saving': 'Guardando…',
    'settings.loading': 'Cargando…',
    'settings.interfaceLanguage': 'Idioma de la interfaz',
  },
};

type TFunction = (key: string, vars?: Record<string, string | number>) => string;

const ItamI18nContext = createContext<{ locale: ItamLocale; t: TFunction } | null>(null);

function substitute(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return Object.entries(vars).reduce(
    (acc, [key, value]) => acc.split(`{${key}}`).join(String(value)),
    template
  );
}

export function ItamI18nProvider({ locale, children }: { locale: ItamLocale; children: React.ReactNode }) {
  const value = useMemo(() => {
    const t: TFunction = (key, vars) => {
      const active = DICTIONARIES[locale] || DICTIONARIES.en;
      // Look up the key in the active locale, fall back to `en`, then to the key itself —
      // never render an empty string for a missing key.
      const template = active[key] ?? DICTIONARIES.en[key] ?? key;
      return substitute(template, vars);
    };
    return { locale, t };
  }, [locale]);

  return <ItamI18nContext.Provider value={value}>{children}</ItamI18nContext.Provider>;
}

export function useItamT(): TFunction {
  const ctx = useContext(ItamI18nContext);
  // Outside a provider (e.g. a panel rendered in isolation in a test), fall back to
  // English lookups rather than throwing — this is a lookup-with-fallback utility, not a
  // hard dependency.
  if (!ctx) {
    return (key, vars) => substitute(DICTIONARIES.en[key] ?? key, vars);
  }
  return ctx.t;
}

// Exported for the SettingsPanel language selector and the dictionary-parity test.
export { DICTIONARIES };
export const SUPPORTED_ITAM_LOCALES: { value: ItamLocale; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español' },
];
