import React, { useState, useEffect } from 'react';
import toastContainer from './ToastContainer';

interface ToastProps {
    title: string;
    message: string;
    severity: 'critical' | 'warning' | 'info';
    autoCloseMs?: number;
}

export const Toast: React.FC<ToastProps> = ({
    title,
    message,
    severity,
    autoCloseMs = 5000,
}) => {
    const [visible, setVisible] = useState(true);

    useEffect(() => {
        const timer = setTimeout(() => setVisible(false), autoCloseMs);
        return () => clearTimeout(timer);
    }, [autoCloseMs]);

    if (!visible) return null;

    return (
        <div className="fixed top-4 right-4 z-50 toast toast-{severity}" onClick={() => setVisible(false)}>
            <div className="flex items-center space-x-3">
                <div className="flex-1">{title}</div>
                <div className="flex-1">{message}</div>
                <button
                    className="text-gray-400 hover:text-gray-700"
                    onClick={() => setVisible(false)}
                >
                    ✕
                </button>
            </div>
        </div>
    );
};