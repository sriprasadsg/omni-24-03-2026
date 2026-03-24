import React, { useState } from 'react';

const API = '/api';
function getHeaders(): HeadersInit {
    const keys = ['access_token', 'token', 'authToken', 'auth.access_token'];
    let token = '';
    for (const k of keys) { token = localStorage.getItem(k) || ''; if (token) break; }
    return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

interface MFASetupWizardProps {
    onClose: () => void;
    onEnabled: () => void;
}

export default function MFASetupWizard({ onClose, onEnabled }: MFASetupWizardProps) {
    const [step, setStep] = useState<1 | 2 | 3>(1);
    const [secret, setSecret] = useState('');
    const [qrBase64, setQrBase64] = useState('');
    const [qrUri, setQrUri] = useState('');
    const [code, setCode] = useState('');
    const [backupCodes, setBackupCodes] = useState<string[]>([]);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const startSetup = async () => {
        setLoading(true); setError('');
        try {
            const r = await fetch(`${API}/mfa/setup`, { headers: getHeaders() });
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || 'Setup failed');
            setSecret(d.secret);
            setQrBase64(d.qr_base64);
            setQrUri(d.qr_uri);
            setStep(2);
        } catch (e: any) { setError(e.message); }
        finally { setLoading(false); }
    };

    const verifySetup = async () => {
        if (code.length !== 6) { setError('Enter the 6-digit code from your authenticator app'); return; }
        setLoading(true); setError('');
        try {
            const r = await fetch(`${API}/mfa/verify-setup`, {
                method: 'POST', headers: getHeaders(),
                body: JSON.stringify({ totp_code: code }),
            });
            const d = await r.json();
            if (!r.ok) throw new Error(d.detail || 'Verification failed');
            setBackupCodes(d.backup_codes || []);
            setStep(3);
        } catch (e: any) { setError(e.message); }
        finally { setLoading(false); }
    };

    const downloadBackupCodes = () => {
        const blob = new Blob([backupCodes.join('\n')], { type: 'text/plain' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = 'mfa-backup-codes.txt'; a.click();
    };

    return (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
            <div style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 16, padding: 32, width: 480, maxWidth: '90vw', color: '#f1f5f9' }}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                    <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#7c3aed' }}>🔐 Set Up Two-Factor Authentication</h2>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 20 }}>✕</button>
                </div>

                {/* Steps indicator */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
                    {[1, 2, 3].map(s => (
                        <div key={s} style={{ flex: 1, height: 4, borderRadius: 4, background: step >= s ? '#7c3aed' : '#334155' }} />
                    ))}
                </div>

                {/* Step 1 — intro */}
                {step === 1 && (
                    <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 64, marginBottom: 16 }}>📱</div>
                        <h3 style={{ margin: '0 0 12px', color: '#e2e8f0' }}>Authenticator App Required</h3>
                        <p style={{ color: '#94a3b8', marginBottom: 24 }}>
                            You'll need <strong>Google Authenticator</strong>, <strong>Authy</strong>, or <strong>Microsoft Authenticator</strong> installed on your phone.
                        </p>
                        {error && <p style={{ color: '#ef4444', marginBottom: 16 }}>{error}</p>}
                        <button onClick={startSetup} disabled={loading}
                            style={{ background: '#7c3aed', color: 'white', border: 'none', borderRadius: 8, padding: '12px 32px', cursor: 'pointer', fontSize: 16, fontWeight: 600 }}>
                            {loading ? 'Generating...' : 'Get Started'}
                        </button>
                    </div>
                )}

                {/* Step 2 — QR code */}
                {step === 2 && (
                    <div>
                        <p style={{ color: '#94a3b8', marginBottom: 16 }}>Scan this QR code with your authenticator app, then enter the 6-digit code below:</p>
                        {qrBase64 ? (
                            <div style={{ textAlign: 'center', marginBottom: 16 }}>
                                <img src={`data:image/png;base64,${qrBase64}`} alt="MFA QR Code" style={{ width: 180, height: 180, borderRadius: 8 }} />
                            </div>
                        ) : (
                            <p style={{ color: '#94a3b8', fontSize: 12, wordBreak: 'break-all', background: '#1e293b', padding: 12, borderRadius: 8, marginBottom: 16 }}>
                                <strong>Manual entry key:</strong><br />{secret}
                            </p>
                        )}
                        <p style={{ color: '#64748b', fontSize: 12, marginBottom: 16 }}>
                            Manual key: <code style={{ color: '#a78bfa' }}>{secret}</code>
                        </p>
                        <input
                            value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                            placeholder="Enter 6-digit TOTP code" maxLength={6}
                            style={{ width: '100%', padding: 12, background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#f1f5f9', fontSize: 18, letterSpacing: 8, textAlign: 'center', boxSizing: 'border-box', marginBottom: 12 }}
                        />
                        {error && <p style={{ color: '#ef4444', marginBottom: 8 }}>{error}</p>}
                        <button onClick={verifySetup} disabled={loading || code.length !== 6}
                            style={{ width: '100%', background: '#7c3aed', color: 'white', border: 'none', borderRadius: 8, padding: 12, cursor: 'pointer', fontSize: 15, fontWeight: 600, opacity: code.length !== 6 ? 0.5 : 1 }}>
                            {loading ? 'Verifying...' : 'Verify & Enable MFA'}
                        </button>
                    </div>
                )}

                {/* Step 3 — backup codes */}
                {step === 3 && (
                    <div>
                        <div style={{ textAlign: 'center', marginBottom: 16 }}>
                            <div style={{ fontSize: 48 }}>✅</div>
                            <h3 style={{ color: '#22c55e', margin: '8px 0' }}>MFA Enabled!</h3>
                        </div>
                        <div style={{ background: '#1e293b', border: '1px solid #7c3aed', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                            <p style={{ color: '#fbbf24', fontWeight: 600, margin: '0 0 12px' }}>⚠️ Save these backup codes — they can only be used once each:</p>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                {backupCodes.map((c, i) => (
                                    <code key={i} style={{ background: '#0f172a', padding: '6px 10px', borderRadius: 6, color: '#a78bfa', textAlign: 'center', letterSpacing: 2 }}>{c}</code>
                                ))}
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: 12 }}>
                            <button onClick={downloadBackupCodes}
                                style={{ flex: 1, background: '#1e293b', color: '#a78bfa', border: '1px solid #7c3aed', borderRadius: 8, padding: 12, cursor: 'pointer', fontWeight: 600 }}>
                                💾 Download Codes
                            </button>
                            <button onClick={() => { onEnabled(); onClose(); }}
                                style={{ flex: 1, background: '#7c3aed', color: 'white', border: 'none', borderRadius: 8, padding: 12, cursor: 'pointer', fontWeight: 600 }}>
                                Done ✓
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
