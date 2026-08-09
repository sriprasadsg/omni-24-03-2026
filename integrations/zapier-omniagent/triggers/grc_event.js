'use strict';

// REST Hook trigger against the platform's existing /api/webhooks CRUD.
// Subscription id comes back from performSubscribe and is persisted by
// Zapier as bundle.subscribeData; performUnsubscribe keys on it, which is
// what prevents duplicate subscriptions across Zap re-enables.

const performSubscribe = (z, bundle) =>
  z
    .request({
      url: `${bundle.authData.baseUrl}/api/webhooks`,
      method: 'POST',
      headers: { 'X-API-Key': bundle.authData.apiKey },
      body: {
        name: 'Zapier trigger',
        url: bundle.targetUrl,
        events: [bundle.inputData.event],
      },
    })
    .then((response) => response.data);

const performUnsubscribe = (z, bundle) =>
  z
    .request({
      url: `${bundle.authData.baseUrl}/api/webhooks/${bundle.subscribeData.id}`,
      method: 'DELETE',
      headers: { 'X-API-Key': bundle.authData.apiKey },
    })
    .then((response) => response.data);

// Required BasicHookOperationSchema fallback: powers the Zap editor's
// "test trigger" UI by reusing the existing deliveries endpoint — the
// platform does not (and should not) grow a second events feed for this.
const performList = (z, bundle) =>
  z
    .request({
      url: `${bundle.authData.baseUrl}/api/webhooks/${bundle.subscribeData ? bundle.subscribeData.id : ''}/deliveries`,
      headers: { 'X-API-Key': bundle.authData.apiKey },
    })
    .then((response) => response.data);

// Inbound signed POST from the platform (see README for X-Webhook-Signature
// verification guidance).
const perform = (z, bundle) => [bundle.cleanedRequest];

module.exports = {
  key: 'grc_event',
  noun: 'GRC Event',
  display: {
    label: 'GRC Event',
    description:
      'Triggers when the OmniAgent platform emits a subscribed GRC event (agent offline, security alert, compliance violation).',
  },
  operation: {
    type: 'hook',
    inputFields: [
      {
        key: 'event',
        label: 'Event',
        type: 'string',
        required: true,
        choices: {
          'agent.offline': 'Agent Offline',
          'security.alert': 'Security Alert',
          'compliance.violation': 'Compliance Violation',
        },
        helpText: 'The OmniAgent platform event that triggers this Zap.',
      },
    ],
    performSubscribe,
    performUnsubscribe,
    performList,
    perform,
    sample: {
      event: 'security.alert',
      timestamp: '2026-07-13T00:00:00Z',
      data: {
        severity: 'high',
        message: 'Sample security alert',
      },
    },
  },
};
