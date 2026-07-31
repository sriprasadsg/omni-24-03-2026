'use strict';

// API-key + base-URL auth. The connection test hits an authenticated platform
// route so Zapier can validate the credentials before saving the connection.
module.exports = {
  type: 'custom',
  fields: [
    {
      key: 'baseUrl',
      label: 'Base URL',
      type: 'string',
      required: true,
      helpText:
        'Base URL of your OmniAgent platform instance, e.g. `https://portal.example.com` (no trailing slash).',
    },
    {
      key: 'apiKey',
      label: 'API Key',
      type: 'password',
      required: true,
      helpText:
        'Tenant API key generated in OmniAgent under **Tenant Settings → API Keys**. Sent as the `X-API-Key` header.',
    },
  ],
  test: (z, bundle) =>
    z
      .request({
        url: `${bundle.authData.baseUrl}/api/webhooks`,
        headers: { 'X-API-Key': bundle.authData.apiKey },
      })
      .then((response) => response.data),
  connectionLabel: (z, bundle) => bundle.authData.baseUrl,
};
