const pkg = require('../package.json');

module.exports = {
  ...pkg.build,
  extraResources: [
    ...pkg.build.extraResources,
    {
      from: 'build/embedded-runtime',
      to: 'app/runtime',
      filter: [
        '!**/__pycache__{,/**/*}',
        '!**/*.pyc',
        '!**/.git{,/**/*}',
      ],
    },
  ],
};
