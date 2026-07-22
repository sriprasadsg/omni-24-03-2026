
import React, { useState } from 'react';
import { CloudAccount, CloudProvider } from '../types';
import { InfoIcon } from './icons';
import { showToast } from '../utils/toast';
import { Modal } from './Modal';

interface AddCloudAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (data: Omit<CloudAccount, 'id' | 'tenantId' | 'status'> & { credentials?: Record<string, string> }) => void;
}

interface ProviderMeta {
  label: string;
  accountIdLabel: string;
  accountIdPlaceholder: string;
  color: string;
}

const PROVIDER_META: Record<CloudProvider, ProviderMeta> = {
  AWS:          { label: 'Amazon Web Services',   accountIdLabel: 'Account ID',       accountIdPlaceholder: '123456789012',          color: 'border-orange-400' },
  Azure:        { label: 'Microsoft Azure',        accountIdLabel: 'Subscription ID',  accountIdPlaceholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', color: 'border-blue-400' },
  GCP:          { label: 'Google Cloud Platform',  accountIdLabel: 'Project ID',       accountIdPlaceholder: 'my-gcp-project',        color: 'border-green-400' },
  OCI:          { label: 'Oracle Cloud (OCI)',     accountIdLabel: 'Tenancy OCID',     accountIdPlaceholder: 'ocid1.tenancy.oc1...',  color: 'border-red-400' },
  IBM:          { label: 'IBM Cloud',              accountIdLabel: 'Account ID',       accountIdPlaceholder: 'ibm-account-id',        color: 'border-indigo-400' },
  Alibaba:      { label: 'Alibaba Cloud',          accountIdLabel: 'Account ID',       accountIdPlaceholder: '1234567890123456',      color: 'border-yellow-400' },
  DigitalOcean: { label: 'DigitalOcean',           accountIdLabel: 'Team Slug',        accountIdPlaceholder: 'my-do-team',            color: 'border-cyan-400' },
  Cloudflare:   { label: 'Cloudflare',             accountIdLabel: 'Account ID',       accountIdPlaceholder: 'cf-account-id',         color: 'border-orange-300' },
  VMware:       { label: 'VMware vSphere',         accountIdLabel: 'vCenter URL',      accountIdPlaceholder: 'vcenter.example.com',   color: 'border-slate-400' },
  Huawei:       { label: 'Huawei Cloud',           accountIdLabel: 'Account ID',       accountIdPlaceholder: 'huawei-account-id',     color: 'border-rose-400' },
};

const ALL_PROVIDERS = Object.keys(PROVIDER_META) as CloudProvider[];

export const AddCloudAccountModal: React.FC<AddCloudAccountModalProps> = ({ isOpen, onClose, onSave }) => {
  const [provider, setProvider] = useState<CloudProvider>('AWS');
  const [name, setName] = useState('');
  const [accountId, setAccountId] = useState('');
  const [accessKey, setAccessKey] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [ociTenancyOcid, setOciTenancyOcid] = useState('');
  const [ociUserOcid, setOciUserOcid] = useState('');
  const [ociFingerprint, setOciFingerprint] = useState('');
  const [ociPrivateKey, setOciPrivateKey] = useState('');
  const [ociRegion, setOciRegion] = useState('');
  const [ociCompartmentId, setOciCompartmentId] = useState('');
  const [regionId, setRegionId] = useState('');
  const [cfApiToken, setCfApiToken] = useState('');
  const [cfAccountId, setCfAccountId] = useState('');

  const meta = PROVIDER_META[provider];

  const resetCredentialFields = () => {
    setAccessKey(''); setSecretKey('');
    setOciTenancyOcid(''); setOciUserOcid(''); setOciFingerprint(''); setOciPrivateKey('');
    setOciRegion(''); setOciCompartmentId('');
    setRegionId(''); setCfApiToken(''); setCfAccountId('');
  };

  const buildCredentials = (): Record<string, string> => {
    if (provider === 'OCI') {
      return {
        oci_tenancy_ocid: ociTenancyOcid,
        oci_user_ocid: ociUserOcid,
        oci_fingerprint: ociFingerprint,
        oci_private_key: ociPrivateKey,
        oci_region: ociRegion,
        oci_compartment_id: ociCompartmentId,
      };
    }
    if (provider === 'Alibaba') {
      return {
        access_key_id: accessKey,
        access_key_secret: secretKey,
        region_id: regionId,
      };
    }
    if (provider === 'Cloudflare') {
      return {
        cf_api_token: cfApiToken,
        cf_account_id: cfAccountId,
      };
    }
    return { accessKey, secretKey };
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !accountId.trim()) {
      showToast('Please fill all required fields.', 'error');
      return;
    }
    const credentials = buildCredentials();
    onSave({ provider, name, accountId, credentials });
    setName(''); setAccountId(''); resetCredentialFields();
  };

  const footer = (
    <>
      <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-medium border rounded-md dark:border-gray-600 dark:text-gray-300">Cancel</button>
      <button type="submit" form="add-cloud-account-form" className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700">Add and Connect</button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add Cloud Account" size="lg" footer={footer}>
        <form id="add-cloud-account-form" onSubmit={handleSubmit} className="space-y-4">
          <style>{`.input-style { padding: 0.5rem 0.75rem; background-color: white; border: 1px solid #d1d5db; border-radius: 0.375rem; } .dark .input-style { background-color: #374151; border-color: #4b5563; color: white; }`}</style>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Cloud Provider</label>
            <div className="grid grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
              {ALL_PROVIDERS.map(p => (
                <label key={p} className={`flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer text-sm transition-colors ${
                  provider === p ? `${PROVIDER_META[p].color} bg-gray-50 dark:bg-gray-700 font-semibold` : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'
                }`}>
                  <input type="radio" name="provider" value={p} checked={provider === p}
                    onChange={() => { setProvider(p); setAccountId(''); }} className="sr-only" />
                  <span className="text-gray-800 dark:text-gray-100 text-xs leading-tight">{PROVIDER_META[p].label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Account Name *</label>
              <input id="name" value={name} onChange={e => setName(e.target.value)} required
                placeholder={`e.g., Production ${provider}`} className="mt-1 block w-full input-style" />
            </div>
            <div>
              <label htmlFor="accountId" className="block text-sm font-medium text-gray-700 dark:text-gray-300">{meta.accountIdLabel} *</label>
              <input id="accountId" value={accountId} onChange={e => setAccountId(e.target.value)} required
                placeholder={meta.accountIdPlaceholder} className="mt-1 block w-full input-style" />
            </div>
          </div>

          <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Credentials (optional)</h3>
            {provider === 'OCI' ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <input value={ociTenancyOcid} onChange={e => setOciTenancyOcid(e.target.value)} placeholder="Tenancy OCID" className="w-full input-style" />
                <input value={ociUserOcid} onChange={e => setOciUserOcid(e.target.value)} placeholder="User OCID" className="w-full input-style" />
                <input value={ociFingerprint} onChange={e => setOciFingerprint(e.target.value)} placeholder="Key Fingerprint" className="w-full input-style" />
                <input value={ociRegion} onChange={e => setOciRegion(e.target.value)} placeholder="Region (e.g. us-ashburn-1)" className="w-full input-style" />
                <input value={ociCompartmentId} onChange={e => setOciCompartmentId(e.target.value)} placeholder="Compartment OCID" className="w-full input-style sm:col-span-2" />
                <textarea value={ociPrivateKey} onChange={e => setOciPrivateKey(e.target.value)} placeholder="Private Key (PEM)" rows={3}
                  className="w-full input-style sm:col-span-2 font-mono text-xs" />
              </div>
            ) : provider === 'Alibaba' ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <input value={accessKey} onChange={e => setAccessKey(e.target.value)} placeholder="Access Key ID" className="w-full input-style" />
                <input type="password" value={secretKey} onChange={e => setSecretKey(e.target.value)} placeholder="Access Key Secret" className="w-full input-style" />
                <input value={regionId} onChange={e => setRegionId(e.target.value)} placeholder="Region ID (e.g. cn-hangzhou)" className="w-full input-style sm:col-span-2" />
              </div>
            ) : provider === 'Cloudflare' ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <input type="password" value={cfApiToken} onChange={e => setCfApiToken(e.target.value)} placeholder="API Token" className="w-full input-style" />
                <input value={cfAccountId} onChange={e => setCfAccountId(e.target.value)} placeholder="Cloudflare Account ID" className="w-full input-style" />
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <input value={accessKey} onChange={e => setAccessKey(e.target.value)} placeholder="Access Key / Client ID" className="w-full input-style" />
                <input type="password" value={secretKey} onChange={e => setSecretKey(e.target.value)} placeholder="Secret Key / Client Secret" className="w-full input-style" />
              </div>
            )}
            <div className="mt-3 p-2 bg-blue-50 dark:bg-blue-900/50 rounded-lg flex items-start text-xs text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
              <InfoIcon size={16} className="mr-2 mt-0.5 flex-shrink-0 text-blue-500" />
              <p>Credentials are stored encrypted. For best security, use a read-only role or service account with minimal permissions.</p>
            </div>
          </div>
        </form>
    </Modal>
  );
};
