import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Clock } from 'lucide-react';
import { Modal } from './Modal';
import { IDLE_TIMEOUT_MINUTES, endSessionForInactivity } from '../services/apiService';

/** Shared across tabs, so working in one tab keeps the others signed in. */
export const LAST_ACTIVITY_KEY = 'omni.lastActivity';
const ACTIVITY_EVENTS = ['keydown', 'pointerdown', 'pointermove', 'wheel', 'scroll', 'touchstart'] as const;
const WRITE_THROTTLE_MS = 5_000;

const readLast = (fallback: number): number => {
    try {
        const v = Number(localStorage.getItem(LAST_ACTIVITY_KEY));
        return Number.isFinite(v) && v > 0 ? v : fallback;
    } catch {
        return fallback;
    }
};

interface IdleSignOutProps {
    timeoutMs?: number;
    warnMs?: number;
    /** Ends the session; defaults to revoking it and showing the login screen with the reason. */
    onSignOut?: () => void | Promise<void>;
}

const fmt = (ms: number) => {
    const s = Math.max(0, Math.ceil(ms / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

/**
 * Automatic sign-out after inactivity (ISO 27001 / SOC 2 "automatic log-off"). Only user input counts
 * as activity, never background polling. Two minutes before the limit a dialog counts down with
 * "Stay signed in"; while it shows, only that button (or activity in another tab) keeps the session.
 */
export const IdleSignOut: React.FC<IdleSignOutProps> = ({
    timeoutMs = IDLE_TIMEOUT_MINUTES * 60_000,
    warnMs = 2 * 60_000,
    onSignOut = endSessionForInactivity,
}) => {
    const lastLocal = useRef(Date.now());
    const lastWrite = useRef(0);
    const signingOut = useRef(false);
    const [remaining, setRemaining] = useState<number | null>(null); // ms left while warning
    const warningRef = useRef(false);
    warningRef.current = remaining !== null;

    const markActive = useCallback((force = false) => {
        const now = Date.now();
        lastLocal.current = now;
        if (force || now - lastWrite.current > WRITE_THROTTLE_MS) {
            lastWrite.current = now;
            try { localStorage.setItem(LAST_ACTIVITY_KEY, String(now)); } catch { /* this tab still tracks it */ }
        }
    }, []);

    const check = useCallback(() => {
        if (signingOut.current) return;
        const last = Math.max(lastLocal.current, readLast(lastLocal.current));
        const left = timeoutMs - (Date.now() - last);
        if (left <= 0) {
            signingOut.current = true;
            setRemaining(null);
            void onSignOut();
        } else if (left <= warnMs) {
            setRemaining(left);
        } else if (warningRef.current) {
            setRemaining(null); // another tab saw activity
        }
    }, [timeoutMs, warnMs, onSignOut]);

    useEffect(() => {
        markActive(true); // signing in counts as activity
        const onActivity = () => { if (!warningRef.current) markActive(); };
        // Capture: scroll does not bubble, and the app scrolls inside <main>, not the window.
        ACTIVITY_EVENTS.forEach(e => window.addEventListener(e, onActivity, { passive: true, capture: true }));
        const onVisible = () => { if (document.visibilityState === 'visible') check(); };
        document.addEventListener('visibilitychange', onVisible);
        window.addEventListener('storage', check);
        const timer = window.setInterval(check, 1_000);
        return () => {
            ACTIVITY_EVENTS.forEach(e => window.removeEventListener(e, onActivity, { capture: true }));
            document.removeEventListener('visibilitychange', onVisible);
            window.removeEventListener('storage', check);
            window.clearInterval(timer);
        };
    }, [markActive, check]);

    const stay = () => { markActive(true); setRemaining(null); };
    const signOutNow = () => { signingOut.current = true; setRemaining(null); void onSignOut(); };

    return (
        <Modal
            isOpen={remaining !== null}
            onClose={stay}
            title="Still there?"
            icon={<Clock className="h-5 w-5 text-amber-500" />}
            size="sm"
            closeOnBackdrop={false}
            footer={
                <div className="flex justify-end gap-2 w-full">
                    <button onClick={signOutNow} className="h-9 px-4 rounded-xl text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-900/[0.05] dark:hover:bg-white/[0.07] transition-colors">
                        Sign out now
                    </button>
                    <button onClick={stay} className="h-9 px-4 rounded-xl text-sm font-semibold text-white bg-primary-600 hover:bg-primary-700 transition-colors">
                        Stay signed in
                    </button>
                </div>
            }
        >
            <p className="text-sm text-gray-600 dark:text-gray-300">
                For security, you will be signed out after {Math.round(timeoutMs / 60_000)} minutes without activity.
            </p>
            <p className="mt-3 text-3xl font-semibold tabular-nums text-gray-900 dark:text-white" aria-hidden="true">{fmt(remaining ?? 0)}</p>
            <p className="sr-only">You will be signed out in about {Math.ceil((remaining ?? 0) / 60_000)} minutes.</p>
        </Modal>
    );
};
