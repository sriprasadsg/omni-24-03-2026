import type {
	IAuthenticateGeneric,
	ICredentialType,
	INodeProperties,
} from 'n8n-workflow';

export class OmniAgentApi implements ICredentialType {
	name = 'omniAgentApi';

	displayName = 'OmniAgent API';

	documentationUrl = 'https://github.com/omniagent/n8n-nodes-omniagent#readme';

	properties: INodeProperties[] = [
		{
			displayName: 'Base URL',
			name: 'baseUrl',
			type: 'string',
			default: '',
			placeholder: 'https://portal.example.com',
			description: 'Base URL of your OmniAgent platform instance (no trailing slash)',
			required: true,
		},
		{
			displayName: 'API Key',
			name: 'apiKey',
			type: 'string',
			typeOptions: { password: true },
			default: '',
			description:
				'Tenant API key generated in OmniAgent under Tenant Settings → API Keys. Sent as the X-API-Key header.',
			required: true,
		},
	];

	authenticate: IAuthenticateGeneric = {
		type: 'generic',
		properties: {
			headers: {
				'X-API-Key': '={{$credentials.apiKey}}',
			},
		},
	};
}
