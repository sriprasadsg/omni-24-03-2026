import React, { useEffect, useId, useRef, useState } from 'react';
import { Modal } from '../Modal';
import { ACCENT_BUTTON } from '../AutonomousOpsResponseSettingsDialogs';
import { HealthNotice } from '../AutonomousOpsHealthChips';
import { AlertTriangleIcon, ClockIcon } from '../icons';
import { downloadAutonomousOpsExport } from '../../services/autonomousOpsReporting';
import type { ExportDays, ExportFormat, ExportOutcome } from '../../services/autonomousOpsReporting';
import type { AutonomousOpsBucket, AutonomousOpsApiError } from '../../services/autonomousOpsApi';
import { showToast } from '../../utils/toast';
import {
    EXPORT_AUDIT_SENTENCE, EXPORT_CLOSE, EXPORT_EMPTY, EXPORT_ERROR, EXPORT_FORBIDDEN, EXPORT_PREPARING, EXPORT_TITLE,
    FORMAT_LEGEND, FORMAT_OPTIONS, PERIOD_LEGEND, PERIOD_OPTIONS, capNote, exportButton, exportToast, includedLine,
} from './reportingCopy';

interface ExportDialogProps {
    /** The state pill the Activity list is showing. */
    bucket: AutonomousOpsBucket;
    /** The Statistics period; the dialog opens on it. */
    defaultDays: 7 | 30 | 90;
    /** Platform staff viewing one organization; tenant roles pass nothing. */
    tenantId?: string | null;
    onClose: () => void;
}

const SECONDARY_BUTTON =
    'inline-flex items-center justify-center min-h-10 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ' +
    'px-4 text-sm font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-60';
const ROW = 'flex min-h-10 cursor-pointer items-start gap-2 rounded-lg px-2 py-2 hover:bg-gray-50 dark:hover:bg-white/[0.04]';

/**
 * The Export activity dialog (86-UI-SPEC section 3, ACTV-06). It always opens filled (CSV, the Statistics
 * period) and says exactly what it exports. One request per click; Close stays enabled and Esc is ignored
 * while the file is prepared. A whole file closes the dialog with a toast; a cut file keeps an amber note
 * with the true total; no rows means no file. Every server string (the file name) renders as React text.
 */
export const ExportDialog: React.FC<ExportDialogProps> = ({ bucket, defaultDays, tenantId = null, onClose }) => {
    const uid = useId();
    const [format, setFormat] = useState<ExportFormat>('csv');
    const [days, setDays] = useState<ExportDays>(String(defaultDays) as ExportDays);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<ExportOutcome | null>(null);
    const inFlight = useRef(false);
    const resultRef = useRef<HTMLDivElement>(null);

    // Focus moves to the result block once it replaces the choices.
    useEffect(() => { if (result) resultRef.current?.focus(); }, [result]);

    const submit = async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        setPending(true);
        setError(null);
        try {
            const outcome = await downloadAutonomousOpsExport({ format, bucket, days, tenantId });
            if (outcome.status === 'downloaded' && !outcome.truncated) {
                showToast(exportToast(outcome.rows), 'success');
                onClose();
                return;
            }
            setResult(outcome);
        } catch (e) {
            const err = e as Partial<AutonomousOpsApiError>;
            setError(err.status === 403 ? EXPORT_FORBIDDEN : EXPORT_ERROR);
        } finally {
            inFlight.current = false;
            setPending(false);
        }
    };

    const footer = (
        <>
            <button type="button" className={SECONDARY_BUTTON} onClick={onClose} autoFocus>{EXPORT_CLOSE}</button>
            {!result && (
                <button type="button" className={ACCENT_BUTTON} onClick={() => void submit()} disabled={pending}>
                    {pending ? EXPORT_PREPARING : exportButton(format)}
                </button>
            )}
        </>
    );

    return (
        <Modal isOpen onClose={onClose} title={EXPORT_TITLE} size="md" showClose={false} closeOnBackdrop={false} closeOnEsc={!pending} footer={footer}>
            {result ? (
                <div ref={resultRef} tabIndex={-1} role="status" className="outline-none">
                    {result.status === 'empty' ? (
                        <HealthNotice tone="blue"><p>{EXPORT_EMPTY}</p></HealthNotice>
                    ) : (
                        <HealthNotice tone="amber" icon={ClockIcon}><p className="break-words">{capNote(result.fileName, result.total)}</p></HealthNotice>
                    )}
                </div>
            ) : (
                <div className="flex flex-col gap-4">
                    <fieldset className="flex flex-col gap-1">
                        <legend className="mb-1 text-sm font-semibold text-gray-900 dark:text-white">{FORMAT_LEGEND}</legend>
                        {FORMAT_OPTIONS.map(o => (
                            <label key={o.value} className={ROW}>
                                <input
                                    type="radio" name={`${uid}-format`} value={o.value} checked={format === o.value}
                                    onChange={() => setFormat(o.value)} className="mt-1"
                                />
                                <span className="min-w-0">
                                    <span className="block text-sm font-semibold text-gray-900 dark:text-white">{o.label}</span>
                                    <span className="block break-words text-xs text-gray-500 dark:text-gray-400">{o.helper}</span>
                                </span>
                            </label>
                        ))}
                    </fieldset>
                    <fieldset className="flex flex-col gap-1">
                        <legend className="mb-1 text-sm font-semibold text-gray-900 dark:text-white">{PERIOD_LEGEND}</legend>
                        {PERIOD_OPTIONS.map(o => (
                            <label key={o.value} className={ROW}>
                                <input
                                    type="radio" name={`${uid}-period`} value={o.value} checked={days === o.value}
                                    onChange={() => setDays(o.value)} className="mt-1"
                                />
                                <span className="text-sm text-gray-900 dark:text-white">{o.label}</span>
                            </label>
                        ))}
                    </fieldset>
                    <p role="status" className="break-words text-xs text-gray-500 dark:text-gray-400">{includedLine(bucket, days)}</p>
                    <p className="break-words text-xs text-gray-500 dark:text-gray-400">{EXPORT_AUDIT_SENTENCE}</p>
                    {error && (
                        <div role="alert" className="flex items-start gap-2 break-words rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
                            <AlertTriangleIcon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                            <span className="min-w-0">{error}</span>
                        </div>
                    )}
                </div>
            )}
        </Modal>
    );
};

export default ExportDialog;
