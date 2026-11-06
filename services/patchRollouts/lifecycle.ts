export interface LifecycleResult { status: string; reason: string; ring: string }

export async function resumeRollout(_id: string, _reason: string, _tenantId?: string | null): Promise<LifecycleResult> {
    throw new Error('not implemented');
}

export async function cancelRollout(_id: string, _tenantId?: string | null): Promise<LifecycleResult> {
    throw new Error('not implemented');
}
