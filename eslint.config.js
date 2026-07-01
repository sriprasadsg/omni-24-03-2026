import tseslint from 'typescript-eslint';

export default tseslint.config(
    {
        ignores: [
            'dist/',
            'node_modules/',
            'backend/',
            'agent/',
            'scripts/',
            'version 1/',
            'code-review-graph-main/',
            'client-presentation/',
            '.remember/',
        ],
    },
    ...tseslint.configs.recommended,
    {
        files: ['**/*.ts', '**/*.tsx', '**/*.js'],
        rules: {
            '@typescript-eslint/no-explicit-any': 'off',
            '@typescript-eslint/no-unused-vars': 'off',
            '@typescript-eslint/no-unused-expressions': 'off',
            '@typescript-eslint/no-require-imports': 'off',
            '@typescript-eslint/ban-ts-comment': 'off',
            '@typescript-eslint/no-empty-object-type': 'off',
            'react-hooks/exhaustive-deps': 'off',
            'no-unused-disable-directives': 'off',
        },
    },
);
