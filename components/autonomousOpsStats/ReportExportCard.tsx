import React, { useId, useState } from 'react';
import { useUser } from '../../contexts/UserContext';
import { platformTier } from '../../utils/permissions';
import { showToast } from '../../utils/toast';
import { downloadAutonomousOpsReport } from '../../services/autonomousOpsReporting';
import type { ExportFormat } from '../../services/autonomousOpsReporting';
import { ActivityIcon } from '../icons';
import {
    REPORT_CARD_NOTE, REPORT_CARD_TITLE, REPORT_FAILED_TOAST, REPORT_NEEDS_EXPORT, REPORT_NEEDS_VIEW, REPORT_PLATFORM_STAFF,
    REPORT_TRUNCATED_TOAST,
} from './reportingCopy';

const BUTTON = 'px-3 py-1 text-xs font-medium rounded-md disabled:opacity-50 disabled:cursor-not-allowed flex items-center';
const CSV_BUTTON = `${BUTTON} text-gray-700 bg-gray-200 dark:bg-gray-700 dark:text-gray-200 hover:bg-gray-300`;
const PDF_BUTTON = `${BUTTON} text-red-700 bg-red-100 dark:bg-red-900/50 dark:text-red-300 hover:bg-red-200`;

/**
 * The Autonomous Ops Activity card in the Reporting screen's Data Export Center (86-UI-SPEC section 4, D-09).
 * Same look as the screen's ExportCard, plus a note and, when the buttons are off, the first unmet reason in
 * words: platform staff (no organization to export from), no export:reports, no view:autonomous_ops.
 * The server checks all of it again; this only explains. Every string here is fixed text.
 */
export const ReportExportCard: React.FC = () => {
    const { currentUser, hasPermission } = useUser();
    const reasonId = `${useId()}-reason`;
    const [pending, setPending] = useState<ExportFormat | null>(null);

    const reason = platformTier(currentUser?.role) !== null
        ? REPORT_PLATFORM_STAFF
        : !hasPermission('export:reports')
            ? REPORT_NEEDS_EXPORT
            : !hasPermission('view:autonomous_ops')
                ? REPORT_NEEDS_VIEW
                : null;

    const run = async (format: ExportFormat) => {
        if (reason || pending) return;
        setPending(format);
        try {
            const outcome = await downloadAutonomousOpsReport(format);
            if (outcome.truncated) showToast(REPORT_TRUNCATED_TOAST, 'success');
        } catch {
            showToast(REPORT_FAILED_TOAST, 'error');
        } finally {
            setPending(null);
        }
    };

    const described = reason ? reasonId : undefined;

    return (
        <div className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md flex justify-between items-center gap-4">
            <div className="min-w-0">
                <h4 className="font-semibold text-gray-800 dark:text-white break-words">{REPORT_CARD_TITLE}</h4>
                <p className="text-xs text-gray-500 dark:text-gray-400 break-words">{REPORT_CARD_NOTE}</p>
                {reason && <p id={reasonId} className="mt-1 text-xs text-gray-500 dark:text-gray-400 break-words">{reason}</p>}
            </div>
            <div className="flex space-x-2 shrink-0">
                <button type="button" onClick={() => void run('csv')} disabled={!!reason || !!pending} aria-describedby={described} className={CSV_BUTTON}>
                    {pending === 'csv' ? <ActivityIcon size={14} className="animate-spin mr-1" /> : null}
                    CSV
                </button>
                <button type="button" onClick={() => void run('pdf')} disabled={!!reason || !!pending} aria-describedby={described} className={PDF_BUTTON}>
                    {pending === 'pdf' ? <ActivityIcon size={14} className="animate-spin mr-1" /> : null}
                    PDF
                </button>
            </div>
        </div>
    );
};

export default ReportExportCard;
