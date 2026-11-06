import React from 'react';

interface DialogProps { rolloutId: string; tenantId: string | null; onClose: () => void; onDone: () => void }

export const ResumeDialog: React.FC<DialogProps & { ringName: string }> = () => null;
export const CancelDialog: React.FC<DialogProps & { rolloutName: string; revertRunning: boolean }> = () => null;
