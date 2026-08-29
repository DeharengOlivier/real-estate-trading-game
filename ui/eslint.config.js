/*
 * Static analysis for the browser code, matching what ruff does for the API.
 *
 * Three plugins beyond the recommended JavaScript rules, each for a class of
 * defect this project has actually shipped:
 *
 *   react-hooks  a stale closure in a useEffect dependency list is invisible in
 *                review and shows up as data that silently stops refreshing;
 *   jsx-a11y     the market and portfolio views were built with clickable divs
 *                and unlabelled inputs, which no test would have caught;
 *   react        unkeyed lists and unescaped entities.
 *
 * ESLint is pinned to 9 rather than 10 because eslint-plugin-jsx-a11y does not
 * declare support for 10 yet. Lift the pin when it does.
 */
import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
    },
    rules: {
      ...react.configs.flat.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.recommended.rules,
      // The new JSX transform means React needs no import in scope.
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
    },
  },
  {
    files: ['vite.config.js', 'eslint.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
]
