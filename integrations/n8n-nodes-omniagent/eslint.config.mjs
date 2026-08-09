import n8nNodesBase from 'eslint-plugin-n8n-nodes-base';
import tsParser from '@typescript-eslint/parser';

export default [
  {
    files: ['credentials/**/*.ts'],
    languageOptions: { parser: tsParser, sourceType: 'module' },
    plugins: { 'n8n-nodes-base': n8nNodesBase },
    rules: {
      ...n8nNodesBase.configs.credentials.rules,
      // Main-repo-only rule; community packages use a real HTTP documentationUrl
      // (enforced by cred-class-field-documentation-url-not-http-url instead).
      'n8n-nodes-base/cred-class-field-documentation-url-miscased': 'off',
    },
  },
  {
    files: ['nodes/**/*.ts'],
    languageOptions: { parser: tsParser, sourceType: 'module' },
    plugins: { 'n8n-nodes-base': n8nNodesBase },
    rules: {
      ...n8nNodesBase.configs.nodes.rules,
    },
  },
];
