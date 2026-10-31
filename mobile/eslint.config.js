// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  { ignores: ['dist/*', 'node_modules/*'] },
  {
    rules: {
      // Written for HTML, where a stray quote can break markup; inside React Native <Text> it is plain text.
      'react/no-unescaped-entities': 'off',
    },
  },
]);
