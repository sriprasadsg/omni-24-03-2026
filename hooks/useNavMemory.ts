import { useCallback, useEffect, useState } from 'react';
import { AppView } from '../types';

/**
 * Pinned and recently visited pages, kept per user in this browser (a convenience, not shared state).
 * Storage can be missing or throw (private windows, blocked site data), so every access is guarded and
 * the shell works without it. Callers must still filter the views through the visible menu: a pin
 * never grants a page the user can no longer open.
 */
const MAX_RECENT = 6;
const MAX_PINNED = 12;
const CHANGE_EVENT = 'omni-nav-memory';

const keyFor = (userKey: string, kind: 'pinned' | 'recent') => `omni.nav.${kind}.${userKey}`;

function read(key: string): AppView[] {
    try {
        const raw = localStorage.getItem(key);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed.filter((v): v is AppView => typeof v === 'string') : [];
    } catch {
        return [];
    }
}

function write(key: string, views: AppView[]) {
    try {
        localStorage.setItem(key, JSON.stringify(views));
    } catch {
        /* storage unavailable: keep the in-memory value for this session */
    }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
}

export function useNavMemory(userKey: string | null) {
    const [pinned, setPinned] = useState<AppView[]>(() => (userKey ? read(keyFor(userKey, 'pinned')) : []));
    const [recent, setRecent] = useState<AppView[]>(() => (userKey ? read(keyFor(userKey, 'recent')) : []));

    // Re-read on user change and whenever another component (or tab) changes the lists.
    useEffect(() => {
        if (!userKey) { setPinned([]); setRecent([]); return; }
        const sync = () => {
            setPinned(read(keyFor(userKey, 'pinned')));
            setRecent(read(keyFor(userKey, 'recent')));
        };
        sync();
        window.addEventListener(CHANGE_EVENT, sync);
        window.addEventListener('storage', sync);
        return () => {
            window.removeEventListener(CHANGE_EVENT, sync);
            window.removeEventListener('storage', sync);
        };
    }, [userKey]);

    const togglePin = useCallback((view: AppView) => {
        if (!userKey) return;
        const key = keyFor(userKey, 'pinned');
        const current = read(key);
        const next = current.includes(view) ? current.filter(v => v !== view) : [...current, view].slice(-MAX_PINNED);
        setPinned(next);
        write(key, next);
    }, [userKey]);

    const recordVisit = useCallback((view: AppView) => {
        if (!userKey) return;
        const key = keyFor(userKey, 'recent');
        const current = read(key);
        if (current[0] === view) return;
        const next = [view, ...current.filter(v => v !== view)].slice(0, MAX_RECENT);
        setRecent(next);
        write(key, next);
    }, [userKey]);

    return { pinned, recent, togglePin, recordVisit };
}

/** The per-user key the nav memory is stored under (email + tenant, like the landing key). */
export const navMemoryKey = (user: { email?: string; tenantId?: string } | null | undefined): string | null =>
    user?.email ? `${user.email}|${user.tenantId ?? ''}` : null;
