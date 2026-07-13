import n8nNodesBase from 'eslint-plugin-n8n-nodes-base';

export default [
  {
    files: ['credentials/**/*.ts'],
    plugins: { 'n8n-nodes-base': n8nNodesBase },
    rules: {
      ...n8nNodesBase.configs.credentials.rules,
    },
  },
  {
    files: ['nodes/**/*.ts'],
    plugins: { 'n8n-nodes-base': n8nNodesBase },
    rules: {
      ...n8nNodesBase.configs.nodes.rules,
    },
  },
];
