import { API_BASE, authFetch } from './apiService';

/**
 * Phase 87: the typed client for the three partner surfaces (the Super Admin's Partners page, the
 * Partner portal and the public accept-invite page). Every signed-in call goes through authFetch, which
 * owns the token; only the two invite-page calls use plain fetch, because the person has no session yet.
 * A refusal throws PartnerApiError carrying the server's own wording (body.error, then body.detail),
 * its stable code and any numbers (free, handedOut, ...) so a screen can show the message verbatim.
 */

export type PartnerStatus = 'active' | 'suspended';

export interface PartnerSummary {
  id: string;
  name: string;
  poolSize: number;
  allocated: number;
  free: number;
  expiresAt: string | null;
  expired: boolean;
  screenCeiling: string[];
  unrestricted: boolean;
  status: PartnerStatus;
  customerCount: number;
}

export interface PartnerPool {
  size: number;
  handedOut: number;
  free: number;
  expiresAt: string | null;
  expired: boolean;
}

/** D-01: the only facts a partner may see about a customer. */
export interface PartnerCustomerRow {
  id: string;
  name: string;
  seatsAssigned: number;
  seatsUsed: number;
  agentsOnline: number;
  agentsTotal: number;
  licenseExpiresAt: string | null;
}

export interface PartnerOverview {
  partner: { name: string };
  role: 'admin' | 'viewer';
  pool: PartnerPool;
  ceiling: string[];
  unrestricted: boolean;
  customers: PartnerCustomerRow[];
}

export interface DirectCustomer {
  id: string;
  name: string;
  seatsAssigned: number;
}

export interface CustomerFeatures {
  enabledFeatures: string[];
  ceiling: string[];
  unrestricted: boolean;
  /** Screens the customer already has that sit outside the ceiling (D-19). */
  kept: string[];
}

export type PartnerStaffRole = 'partner_admin' | 'partner_viewer';
export type PartnerStaffStatus = 'active' | 'invited' | 'invite_expired';

export interface PartnerTeamMember {
  id: string;
  name: string;
  email: string;
  role: PartnerStaffRole;
  status: PartnerStaffStatus;
}

export interface InviteStatus {
  state: 'valid' | 'expired' | 'used' | 'invalid';
  organizationName?: string;
  email?: string;
  roleKind?: string;
}

export interface AppointPartnerInput {
  name: string;
  poolSize: number;
  expiresAt?: string | null;
  screenCeiling: string[];
  adminName: string;
  adminEmail: string;
}

/** Only the fields being changed are sent; an explicit null expiresAt clears the pool expiry. */
export interface UpdatePartnerInput {
  name?: string;
  poolSize?: number;
  expiresAt?: string | null;
  screenCeiling?: string[];
}

export interface CreateCustomerInput {
  name: string;
  seats: number;
  enabledFeatures?: string[];
  adminName: string;
  adminEmail: string;
}

export interface ColleagueInput {
  name: string;
  email: string;
  role: PartnerStaffRole;
}

export class PartnerApiError extends Error {
  status: number;
  code?: string;
  data: Record<string, unknown>;

  constructor(message: string, status: number, code?: string, data: Record<string, unknown> = {}) {
    super(message);
    this.name = 'PartnerApiError';
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

async function partnerError(res: Response, fallback: string): Promise<PartnerApiError> {
  const body = await res.json().catch(() => ({}));
  const data: Record<string, unknown> = body && typeof body === 'object' ? body : {};
  const text = [data.error, data.detail].find(v => typeof v === 'string' && v.trim()) as string | undefined;
  const code = typeof data.code === 'string' ? data.code : undefined;
  return new PartnerApiError(text ?? fallback, res.status, code, data);
}

async function readJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw await partnerError(res, fallback);
  return (await res.json()) as T;
}

const jsonBody = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });
const platformUrl = (path = '') => `${API_BASE}/platform/partners${path}`;
const portalUrl = (path = '') => `${API_BASE}/partner${path}`;
const enc = encodeURIComponent;

// --- Super Admin: the Partners page ---

export async function fetchPartners(): Promise<PartnerSummary[]> {
  const data = await readJson<{ partners: PartnerSummary[] }>(await authFetch(platformUrl()), 'Could not load the partners.');
  return data.partners ?? [];
}

export async function appointPartner(input: AppointPartnerInput): Promise<{ partner: PartnerSummary; emailSent: boolean }> {
  return readJson(await authFetch(platformUrl(), jsonBody(input)), 'Could not appoint the partner.');
}

export async function updatePartner(partnerId: string, changes: UpdatePartnerInput): Promise<PartnerSummary> {
  const res = await authFetch(platformUrl(`/${enc(partnerId)}`), { method: 'PATCH', body: JSON.stringify(changes) });
  return (await readJson<{ partner: PartnerSummary }>(res, 'Could not save the changes.')).partner;
}

export async function suspendPartner(partnerId: string): Promise<PartnerSummary> {
  const res = await authFetch(platformUrl(`/${enc(partnerId)}/suspend`), { method: 'POST' });
  return (await readJson<{ partner: PartnerSummary }>(res, 'Could not suspend the partner.')).partner;
}

export async function reinstatePartner(partnerId: string): Promise<PartnerSummary> {
  const res = await authFetch(platformUrl(`/${enc(partnerId)}/reinstate`), { method: 'POST' });
  return (await readJson<{ partner: PartnerSummary }>(res, 'Could not reinstate the partner.')).partner;
}

export async function fetchPartnerCustomers(partnerId: string): Promise<PartnerCustomerRow[]> {
  const res = await authFetch(platformUrl(`/${enc(partnerId)}/customers`));
  return (await readJson<{ customers: PartnerCustomerRow[] }>(res, 'Could not load the customers.')).customers ?? [];
}

export async function fetchDirectCustomers(): Promise<DirectCustomer[]> {
  const res = await authFetch(platformUrl('/direct-customers'));
  return (await readJson<{ customers: DirectCustomer[] }>(res, 'Could not load the direct customers.')).customers ?? [];
}

/** Move a customer to a partner, or back to direct with a null target. */
export async function moveCustomer(customerId: string, targetPartnerId: string | null): Promise<unknown> {
  const res = await authFetch(platformUrl(`/customers/${enc(customerId)}/move`), jsonBody({ targetPartnerId }));
  return readJson(res, 'Could not move the customer.');
}

// --- Partner portal ---

export async function fetchPartnerOverview(): Promise<PartnerOverview> {
  return readJson(await authFetch(portalUrl('/overview')), 'Could not load your customers.');
}

export async function createPartnerCustomer(
  input: CreateCustomerInput,
): Promise<{ customer: PartnerCustomerRow; emailSent: boolean }> {
  return readJson(await authFetch(portalUrl('/customers'), jsonBody(input)), 'Could not create the customer.');
}

export async function changeCustomerSeats(customerId: string, seats: number): Promise<PartnerCustomerRow> {
  const res = await authFetch(portalUrl(`/customers/${enc(customerId)}/seats`), {
    method: 'PUT',
    body: JSON.stringify({ seats }),
  });
  const data = await readJson<{ customer?: PartnerCustomerRow }>(res, 'Could not change the seats.');
  return data.customer as PartnerCustomerRow;
}

export async function fetchCustomerFeatures(customerId: string): Promise<CustomerFeatures> {
  return readJson(await authFetch(portalUrl(`/customers/${enc(customerId)}/features`)), 'Could not load the screens.');
}

export async function saveCustomerFeatures(customerId: string, enabledFeatures: string[]): Promise<CustomerFeatures> {
  const res = await authFetch(portalUrl(`/customers/${enc(customerId)}/features`), {
    method: 'PUT',
    body: JSON.stringify({ enabledFeatures }),
  });
  return readJson(res, 'Could not save the screens.');
}

export async function fetchPartnerTeam(): Promise<PartnerTeamMember[]> {
  const res = await authFetch(portalUrl('/team'));
  return (await readJson<{ members: PartnerTeamMember[] }>(res, 'Could not load your team.')).members ?? [];
}

export async function inviteColleague(input: ColleagueInput): Promise<{ member: PartnerTeamMember; emailSent: boolean }> {
  return readJson(await authFetch(portalUrl('/team'), jsonBody(input)), 'Could not send the invitation.');
}

export async function resendColleagueInvite(userId: string): Promise<{ member?: PartnerTeamMember; emailSent: boolean }> {
  const res = await authFetch(portalUrl(`/team/${enc(userId)}/resend`), { method: 'POST' });
  return readJson(res, 'Could not send the invitation again.');
}

// --- Public accept-invite page: no session yet, so no Authorization header ---

const publicPost = (path: string, body: unknown): Promise<Response> =>
  fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export async function fetchInviteStatus(token: string): Promise<InviteStatus> {
  return readJson(await publicPost('/auth/invite/status', { token }), 'Could not check this link.');
}

export async function acceptInvite(token: string, newPassword: string): Promise<void> {
  const res = await publicPost('/auth/reset-password/confirm', { token, new_password: newPassword });
  if (!res.ok) throw await partnerError(res, 'Could not set the password.');
}
