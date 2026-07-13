'use strict';

const { version: platformVersion } = require('zapier-platform-core');
const packageJson = require('./package.json');

const authentication = require('./authentication');
const grcEvent = require('./triggers/grc_event');

module.exports = {
  version: packageJson.version,
  platformVersion,

  authentication,

  triggers: {
    [grcEvent.key]: grcEvent,
  },
};
