
// This file will be populated with application constants as features are rebuilt.
import { Permission, SubscriptionTier } from './types';

export const ALL_PERMISSIONS: Permission[] = [
  'view:dashboard', 
  'view:reporting',
  'export:reports',
  'view:agents',
  'view:agent_logs',
  'remediate:agents',
  'view:assets', 
  'view:patching',
  'manage:patches',
  'view:security', 
  'manage:security_cases',
  'manage:security_playbooks',
  'investigate:security',
  'view:compliance',
  'manage:compliance_evidence',
  'view:ai_governance',
  'manage:ai_risks',
  'manage:settings',
  'manage:tenants',
  'view:cloud_security',
  'view:finops',
  'view:audit_log',
  'manage:rbac',
  'manage:api_keys',
  'view:logs',
  'view:threat_hunting',
  'view:profile',
  'view:automation',
  'manage:automation',
  'view:devsecops',
  'view:developer_hub',
  'view:insights',
  'view:tracing',
  'view:dspm',
  'view:attack_path',
  'view:service_catalog',
  'view:dora_metrics',
  'view:chaos',
  'view:network',
];

export const AVAILABLE_AGENT_VERSIONS: string[] = ['2.2.1', '2.3.0', '3.0.0-beta'];

export const SUBSCRIPTION_TIERS: Record<Exclude<SubscriptionTier, 'Custom'>, { name: string, permissions: Permission[] }> = {
    Free: {
        name: 'Free Tier',
        permissions: [
            'view:dashboard',
            'view:agents',
            'view:assets',
            'view:profile',
        ]
    },
    Pro: {
        name: 'Pro Tier',
        permissions: [
            'view:reporting',
            'export:reports',
            'view:security',
            'investigate:security',
            'view:compliance',
            'view:logs',
            'manage:settings',
            'manage:rbac',
            'manage:api_keys',
            'view:cloud_security',
        ]
    },
    Enterprise: {
        name: 'Enterprise Tier',
        permissions: ALL_PERMISSIONS.filter(p => p !== 'manage:tenants')
    }
};

// Add lower tier permissions to higher tiers
SUBSCRIPTION_TIERS.Pro.permissions.unshift(...SUBSCRIPTION_TIERS.Free.permissions);
SUBSCRIPTION_TIERS.Enterprise.permissions.unshift(...SUBSCRIPTION_TIERS.Pro.permissions);

// Remove duplicates
SUBSCRIPTION_TIERS.Pro.permissions = [...new Set(SUBSCRIPTION_TIERS.Pro.permissions)];
SUBSCRIPTION_TIERS.Enterprise.permissions = [...new Set(SUBSCRIPTION_TIERS.Enterprise.permissions)];