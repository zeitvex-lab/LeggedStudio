import { ConfigEnv, loadEnv, UserConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import vueJsx from '@vitejs/plugin-vue-jsx';
import { resolve } from 'path';

function pathResolve(dir: string) {
  return resolve(process.cwd(), '.', dir);
}

export default ({ mode }: ConfigEnv): UserConfig => {
  const root = process.cwd();
  const env = loadEnv(mode, root);
  console.log('env', env);
  return {
    base: env.VITE_APP_BASE_PATH,
    resolve: {
      alias: [
        {
          find: /\/#\//,
          replacement: pathResolve('types') + '/'
        },
        {
          find: '@',
          replacement: pathResolve('src') + '/'
        },
        {
          find: '~/',
          replacement: pathResolve('src') + '/'
        }
      ]
    },
    build: {},
    plugins: [
      vue(),
      tailwindcss(),
      vueJsx({
        // options are passed on to @vue/babel-plugin-jsx
      })
    ],
    server: {
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_HOST,
          changeOrigin: true
        }
      }
    }
  };
};
