/**
 * Time Formatting Utilities
 * 
 * Centralized utilities for converting UTC timestamps to local time display.
 * All backend timestamps are stored in UTC, these utilities convert them for display.
 */

/**
 * Format UTC timestamp to local date and time string
 * @param utcTimestamp - ISO 8601 UTC timestamp from backend
 * @returns Formatted local date and time string
 */
export function formatLocalDateTime(utcTimestamp: string | Date | null | undefined): string {
    if (!utcTimestamp) return 'Never';

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return 'Invalid Date';

        return date.toLocaleString(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        });
    } catch (error) {
        console.error('Error formatting date:', error);
        return 'Invalid Date';
    }
}

/**
 * Format UTC timestamp to local date string only
 * @param utcTimestamp - ISO 8601 UTC timestamp from backend
 * @returns Formatted local date string
 */
export function formatLocalDate(utcTimestamp: string | Date | null | undefined): string {
    if (!utcTimestamp) return 'Never';

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return 'Invalid Date';

        return date.toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    } catch (error) {
        console.error('Error formatting date:', error);
        return 'Invalid Date';
    }
}

/**
 * Format UTC timestamp to local time string only
 * @param utcTimestamp - ISO 8601 UTC timestamp from backend
 * @returns Formatted local time string
 */
export function formatLocalTime(utcTimestamp: string | Date | null | undefined): string {
    if (!utcTimestamp) return 'Never';

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return 'Invalid Date';

        return date.toLocaleTimeString(undefined, {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        });
    } catch (error) {
        console.error('Error formatting time:', error);
        return 'Invalid Date';
    }
}

/**
 * Format UTC timestamp to relative time (e.g., "2 hours ago")
 * @param utcTimestamp - ISO 8601 UTC timestamp from backend
 * @returns Relative time string
 */
export function formatRelativeTime(utcTimestamp: string | Date | null | undefined): string {
    if (!utcTimestamp) return 'Never';

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return 'Invalid Date';

        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHour / 24);

        if (diffSec < 60) return 'Just now';
        if (diffMin < 60) return `${diffMin} minute${diffMin !== 1 ? 's' : ''} ago`;
        if (diffHour < 24) return `${diffHour} hour${diffHour !== 1 ? 's' : ''} ago`;
        if (diffDay < 7) return `${diffDay} day${diffDay !== 1 ? 's' : ''} ago`;

        return formatLocalDate(utcTimestamp);
    } catch (error) {
        console.error('Error formatting relative time:', error);
        return 'Invalid Date';
    }
}

/**
 * Format UTC timestamp for chart/graph display (short format)
 * @param utcTimestamp - ISO 8601 UTC timestamp from backend
 * @returns Formatted time for charts (e.g., "01:22 AM")
 */
export function formatChartTime(utcTimestamp: string | Date | null | undefined): string {
    if (!utcTimestamp) return '';

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return '';

        return date.toLocaleTimeString(undefined, {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });
    } catch (error) {
        console.error('Error formatting chart time:', error);
        return '';
    }
}

/**
 * Format UTC timestamp for chart/graph display (date only)
 * @param utcTimestamp - ISO 8601 UTC timestamp from backend
 * @returns Formatted date for charts (e.g., "Jan 26")
 */
export function formatChartDate(utcTimestamp: string | Date | null | undefined): string {
    if (!utcTimestamp) return '';

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return '';

        return date.toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric'
        });
    } catch (error) {
        console.error('Error formatting chart date:', error);
        return '';
    }
}

/**
 * Get current local time as ISO string
 * @returns Current local time in ISO format
 */
export function getCurrentLocalTime(): string {
    return new Date().toISOString();
}

/**
 * Check if a timestamp is within the last N hours
 * @param utcTimestamp - ISO 8601 UTC timestamp from backend
 * @param hours - Number of hours to check
 * @returns True if timestamp is within the last N hours
 */
export function isWithinLastHours(utcTimestamp: string | Date | null | undefined, hours: number): boolean {
    if (!utcTimestamp) return false;

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return false;

        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffHours = diffMs / (1000 * 60 * 60);

        return diffHours <= hours;
    } catch (error) {
        console.error('Error checking time range:', error);
        return false;
    }
}
