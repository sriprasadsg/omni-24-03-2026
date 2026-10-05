import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ErrorBoundary } from '../../components/ErrorBoundary';

const STALE_REACT_MESSAGE = "Cannot read properties of null (reading 'useState')";

const Thrower = ({ message }: { message: string }) => {
    throw new TypeError(message);
};

describe('ErrorBoundary stale-React reload', () => {
    const reload = vi.fn();
    const originalLocation = window.location;

    beforeEach(() => {
        reload.mockReset();
        sessionStorage.clear();
        Object.defineProperty(window, 'location', { configurable: true, value: { ...originalLocation, reload } });
        vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    afterEach(() => {
        Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
        vi.restoreAllMocks();
    });

    it('reloads once on the null hook dispatcher error', () => {
        render(<ErrorBoundary name="Test"><Thrower message={STALE_REACT_MESSAGE} /></ErrorBoundary>);
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('does not reload again if the error recurs right after a reload', () => {
        render(<ErrorBoundary name="Test"><Thrower message={STALE_REACT_MESSAGE} /></ErrorBoundary>);
        render(<ErrorBoundary name="Test"><Thrower message={STALE_REACT_MESSAGE} /></ErrorBoundary>);
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('reloads again once the window has passed', () => {
        sessionStorage.setItem('errorBoundary:staleReactReloadAt', String(Date.now() - 60_000));
        render(<ErrorBoundary name="Test"><Thrower message={STALE_REACT_MESSAGE} /></ErrorBoundary>);
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('does not reload on unrelated errors and shows the fallback', () => {
        render(<ErrorBoundary name="Test"><Thrower message="boom" /></ErrorBoundary>);
        expect(reload).not.toHaveBeenCalled();
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('does not reload when sessionStorage is unavailable', () => {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
        render(<ErrorBoundary name="Test"><Thrower message={STALE_REACT_MESSAGE} /></ErrorBoundary>);
        expect(reload).not.toHaveBeenCalled();
    });
});
