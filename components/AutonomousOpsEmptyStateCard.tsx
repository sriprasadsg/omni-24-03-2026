import React from 'react';

/** Centred card body used for "no activity" and "Select an organization" (UI-SPEC 3d, 3f). */
export const EmptyStateCard: React.FC<{
    icon: React.FC<any>;
    heading: string;
    headingLevel?: 'h2' | 'h3';
    children?: React.ReactNode;
}> = ({ icon: Icon, heading, headingLevel = 'h3', children }) => {
    const Heading = headingLevel;
    return (
        <div className="flex flex-col items-center gap-4 px-8 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100 dark:bg-white/[0.06]">
                <Icon size={24} aria-hidden="true" className="text-gray-500 dark:text-gray-400" />
            </div>
            <Heading className="max-w-prose break-words text-lg font-semibold leading-tight text-gray-900 dark:text-white">{heading}</Heading>
            {children}
        </div>
    );
};
