'use strict';

const assert = require('node:assert');
const nock = require('nock');
const zapier = require('zapier-platform-core');

const App = require('../../index');

const appTester = zapier.createAppTester(App);
zapier.tools.env.inject();

const BASE_URL = 'https://portal.example.com';
const AUTH = { baseUrl: BASE_URL, apiKey: 'omni_sk_testkey' };

describe('triggers.grc_event (REST Hook lifecycle, offline)', () => {
  afterEach(() => nock.cleanAll());

  it('performSubscribe POSTs to /api/webhooks with X-API-Key and returns the subscription id', async () => {
    const scope = nock(BASE_URL, {
      reqheaders: { 'x-api-key': 'omni_sk_testkey' },
    })
      .post('/api/webhooks', (body) => {
        assert.strictEqual(body.name, 'Zapier trigger');
        assert.strictEqual(body.url, 'https://hooks.zapier.com/abc');
        assert.deepStrictEqual(body.events, ['security.alert']);
        return true;
      })
      .reply(200, { id: 'wh-zap-1', status: 'Active' });

    const bundle = {
      authData: AUTH,
      targetUrl: 'https://hooks.zapier.com/abc',
      inputData: { event: 'security.alert' },
    };

    const result = await appTester(
      App.triggers.grc_event.operation.performSubscribe,
      bundle
    );

    assert.strictEqual(result.id, 'wh-zap-1');
    scope.done();
  });

  it('performUnsubscribe DELETEs /api/webhooks/{subscribeData.id} with X-API-Key', async () => {
    const scope = nock(BASE_URL, {
      reqheaders: { 'x-api-key': 'omni_sk_testkey' },
    })
      .delete('/api/webhooks/wh-zap-1')
      .reply(200, { success: true });

    const bundle = {
      authData: AUTH,
      subscribeData: { id: 'wh-zap-1' },
    };

    const result = await appTester(
      App.triggers.grc_event.operation.performUnsubscribe,
      bundle
    );

    assert.strictEqual(result.success, true);
    scope.done();
  });

  it('performList GETs the deliveries endpoint and returns the mocked array', async () => {
    const deliveries = [
      { webhook_id: 'wh-zap-1', event: 'security.alert', success: true },
    ];
    const scope = nock(BASE_URL, {
      reqheaders: { 'x-api-key': 'omni_sk_testkey' },
    })
      .get('/api/webhooks/wh-zap-1/deliveries')
      .reply(200, deliveries);

    const bundle = {
      authData: AUTH,
      subscribeData: { id: 'wh-zap-1' },
    };

    const results = await appTester(
      App.triggers.grc_event.operation.performList,
      bundle
    );

    assert.strictEqual(results.length, 1);
    assert.strictEqual(results[0].event, 'security.alert');
    scope.done();
  });

  it('perform returns the inbound cleaned request body as the trigger output', async () => {
    const bundle = {
      authData: AUTH,
      cleanedRequest: {
        event: 'compliance.violation',
        timestamp: '2026-07-13T00:00:00Z',
        data: { control: 'AC-2' },
      },
    };

    const results = await appTester(
      App.triggers.grc_event.operation.perform,
      bundle
    );

    assert.strictEqual(results.length, 1);
    assert.strictEqual(results[0].event, 'compliance.violation');
  });
});
