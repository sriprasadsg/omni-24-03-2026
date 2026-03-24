import React, { useState, useEffect } from 'react';

const API = '/api';

interface MFAVerifyModalProps {
    mfaSessionToken: string;
    onSuccess: (accessToken: string, user: any) => void;
    onCancel: () => void;
}

export default function MFAVerifyModal({ mfaSessionToken, onSuccess, onCancel }: MFAVerifyModalProps) {
    const [code, setCode] = useState('');
    const [useBackup, setUseBackup] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [timeLeft, setTimeLeft] = useState(30);

    // TOTP 30-second countdown
    useEffect(() => {
        const tick = () => {
            const now = Math.floor(Date.now() / 1000);
            setTimeLeft(30 - (now % 30));
        };
        tick();
        const id = setInterval(tick, 1000);
        return () => clearInterval(id);
    }, []);

    const verify = async () => {
        if (!code) return;
        setLoading(true); setError('');
        try {
            const r = await fetch(`${API}/mfa/verify`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_token: mfaSessionToken,
                    code: code.replace(/\s/g, ''),
                    use_backup_code: useBackup,
                }),
            });
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || 'Verification failed');
            // Store token and notify parent
            localStorage.setItem('access_token', d.access_token);
            onSuccess(d.access_token, d.user);
        } catch (e: any) { setError(e.message); }
        finally { setLoading(false); }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') verify();
    };

    const timerColor = timeLeft <= 5 ? '#ef4444' : timeLeft <= 10 ? '#f97316' : '#22c55e';

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9998 }}>
            <div style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 16, padding: 32, width: 400, maxWidth: '90vw', color: '#f1f5f9' }}>
                {/* Header */}
                <div style={{ textAlign: 'center', marginBottom: 24 }}>
                    <div style={{ fontSize: 48, marginBottom: 8 }}>🔐</div>
                    <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Two-Factor Authentication</h2>
                    <p style={{ color: '#94a3b8', margin: '8px 0 0' }}>
                        {useBackup ? 'Enter one of your 8-digit backup codes' : 'Enter the 6-digit code from your authenticator app'}
                    </p>
                </div>

                {/* TOTP timer (only shown for normal TOTP) */}
                {!useBackup && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 16 }}>
                        <div style={{
                            width: 36, height: 36, borderRadius: '50%', border: `3px solid ${timerColor}`,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            color: timerColor, fontWeight: 700, fontSize: 14,
                        }}>
                            {timeLeft}
                        </div>
                        <span style={{ color: '#64748b', fontSize: 13 }}>seconds remaining</span>
                    </div>
                )}

                {/* Code input */}
                <input
                    value={code}
                    onChange={e => setCode(useBackup ? e.target.value.replace(/\D/g, '').slice(0, 8) : e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder={useBackup ? '12345678' : '123456'}
                    maxLength={useBackup ? 8 : 6}
                    onKeyDown={handleKeyDown}
                    autoFocus
                    style={{
                        width: '100%', padding: 14, background: '#1e293b', border: '1px solid #334155',
                        borderRadius: 10, color: '#f1f5f9', fontSize: 28, letterSpacing: 12,
                        textAlign: 'center', boxSizing: 'border-box', marginBottom: 12, fontFamily: 'monospace',
                    }}
                />

                {error && (
                    <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: 8, padding: '8px 12px', marginBottom: 12, color: '#ef4444', fontSize: 14 }}>
                        {error}
                    </div>
                )}

                {/* Action buttons */}
                <button onClick={verify} disabled={loading || !code}
                    style={{ width: '100%', background: '#7c3aed', color: 'white', border: 'none', borderRadius: 10, padding: 14, cursor: 'pointer', fontSize: 16, fontWeight: 700, marginBottom: 12, opacity: !code ? 0.5 : 1 }}>
                    {loading ? 'Verifying...' : 'Verify'}
                </button>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <button onClick={() => { setUseBackup(!useBackup); setCode(''); setError(''); }}
                        style={{ background: 'none', border: 'none', color: '#7c3aed', cursor: 'pointer', fontSize: 13, textDecoration: 'underline' }}>
                        {useBackup ? '← Use authenticator code' : 'Use backup code instead'}
                    </button>
                    <button onClick={onCancel}
                        style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 13 }}>
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );
}
