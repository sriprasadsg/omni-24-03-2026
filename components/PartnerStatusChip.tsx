import React from 'react';

// RED-phase stubs: the behavior lands in the next commit.
export type PartnerStatusKind = 'active' | 'suspended';
export type StaffStatusKind = 'active' | 'invited' | 'invite_expired';
export const PartnerStatusChip: React.FC<{ kind: PartnerStatusKind }> = () => null;
export const PoolExpiryChip: React.FC<{ expiresAt?: string | null; now?: Date }> = () => null;
export const StaffStatusChip: React.FC<{ status: StaffStatusKind }> = () => null;
export const daysUntil = (_iso: string | null | undefined, _now?: Date): number | null => null;
export const formatDay = (_iso: string | null | undefined): string => '';
