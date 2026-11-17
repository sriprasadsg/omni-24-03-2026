import type React from 'react';

/**
 * Keyboard twin of onClick for clickable elements that are not buttons (cards, table rows):
 * Enter or Space on the focused element clicks it. Keys pressed in a control nested inside
 * (an input, a button) belong to that control and are left alone.
 */
export const activateOnKey = (e: React.KeyboardEvent<HTMLElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        e.currentTarget.click();
    }
};
