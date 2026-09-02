const pkg = require('../package.json');

module.exports = {
  ...pkg.build,
  extraResources: [
    ...pkg.build.extraResources,
    {
      from: 'build/online-bootstrap',
      to: 'app/bootstrap',
      filter: [
        '!**/__pycache__{,/**/*}',
        '!**/*.pyc',
      ],
    },
  ],
};
