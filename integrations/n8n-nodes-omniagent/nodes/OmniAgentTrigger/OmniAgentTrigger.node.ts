import type {
	IHookFunctions,
	IWebhookFunctions,
	INodeType,
	INodeTypeDescription,
	IWebhookResponseData,
} from 'n8n-workflow';

export class OmniAgentTrigger implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'OmniAgent Trigger',
		name: 'omniAgentTrigger',
		icon: 'file:omniagent.svg',
		group: ['trigger'],
		version: 1,
		description: 'Starts a workflow when the OmniAgent GRC platform emits a subscribed event',
		defaults: {
			name: 'OmniAgent Trigger',
		},
		inputs: [],
		outputs: ['main'],
		credentials: [
			{
				name: 'omniAgentApi',
				required: true,
			},
		],
		webhooks: [
			{
				name: 'default',
				httpMethod: 'POST',
				responseMode: 'onReceived',
				path: 'webhook',
			},
		],
		properties: [
			{
				displayName: 'Event',
				name: 'event',
				type: 'options',
				// Only the event types the platform actually emits today — do not
				// list aspirational events that would never fire.
				options: [
					{ name: 'Agent Offline', value: 'agent.offline' },
					{ name: 'Security Alert', value: 'security.alert' },
					{ name: 'Compliance Violation', value: 'compliance.violation' },
				],
				default: 'security.alert',
				description: 'The OmniAgent platform event that triggers this workflow',
			},
		],
	};

	webhookMethods = {
		default: {
			async checkExists(this: IHookFunctions): Promise<boolean> {
				// Idempotent subscribe: re-activation must not create a duplicate
				// subscription in the platform's db.webhooks.
				const webhookData = this.getWorkflowStaticData('node');
				return !!webhookData.webhookId;
			},

			async create(this: IHookFunctions): Promise<boolean> {
				const webhookUrl = this.getNodeWebhookUrl('default');
				const event = this.getNodeParameter('event') as string;
				const credentials = await this.getCredentials('omniAgentApi');

				const response = await this.helpers.httpRequest({
					method: 'POST',
					url: `${credentials.baseUrl}/api/webhooks`,
					headers: { 'X-API-Key': credentials.apiKey as string },
					body: {
						name: 'n8n trigger',
						url: webhookUrl,
						events: [event],
					},
					json: true,
				});

				this.getWorkflowStaticData('node').webhookId = response.id;
				return true;
			},

			async delete(this: IHookFunctions): Promise<boolean> {
				const webhookData = this.getWorkflowStaticData('node');
				if (!webhookData.webhookId) {
					return true;
				}
				const credentials = await this.getCredentials('omniAgentApi');

				await this.helpers.httpRequest({
					method: 'DELETE',
					url: `${credentials.baseUrl}/api/webhooks/${webhookData.webhookId}`,
					headers: { 'X-API-Key': credentials.apiKey as string },
				});

				delete webhookData.webhookId;
				return true;
			},
		},
	};

	async webhook(this: IWebhookFunctions): Promise<IWebhookResponseData> {
		const body = this.getBodyData();
		return {
			workflowData: [this.helpers.returnJsonArray(body)],
		};
	}
}
