import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/connect/:ipPort',
    redirect: (to) => {
      const ipPort = to.params.ipPort as string;
      const parts = ipPort.split(':');

      if (parts.length >= 2) {
        const port = parts.pop();
        const ip = parts.join(':');

        return {
          path: '/',
          query: {
            autoConnect: 'true',
            ip: ip,
            port: port
          }
        };
      }

      return { path: '/' };
    }
  },
  {
    path: '/',
    meta: {
      title: 'root'
    },
    component: () => import('@/layout/Index.vue'),
    children: [
      {
        path: '',
        redirect: '/system'
      },
      {
        path: '/System',
        meta: {
          title: 'System'
        },
        children: [
          {
            name: 'system-list',
            path: '',
            component: () => import('@/pages/system/Index.vue')
          },
          {
            path: ':id',
            name: 'system-detail',
            meta: {
              title: 'System Detail',
              menuKey: '/system'
            },
            component: () => import('@/pages/system/Detail.vue')
          }
        ]
      },
      {
        path: '/Node',
        meta: {
          title: 'Node'
        },
        children: [
          {
            name: 'node-list',
            path: '',
            component: () => import('@/pages/node/Index.vue')
          },
          {
            path: ':nodeName',
            name: 'node-detail',
            meta: {
              title: 'Node Detail',
              menuKey: '/node'
            },
            component: () => import('@/pages/node/Detail.vue')
          },
          {
            path: ':nodeName/module/:moduleId',
            name: 'module-detail',
            meta: {
              title: 'Module Detail',
              menuKey: '/node',
              breadcrumbParent: 'node-detail'
            },
            component: () => import('@/pages/module/Detail.vue')
          }
        ]
      },
      {
        path: '/Rpc',
        meta: {
          title: 'Rpc'
        },
        children: [
          {
            name: 'rpc-list',
            path: '',
            component: () => import('@/pages/rpc/Index.vue')
          },
          {
            path: ':funcName',
            name: 'rpc-detail',
            meta: {
              title: 'RPC Detail',
              menuKey: '/rpc'
            },
            component: () => import('@/pages/rpc/Detail.vue')
          }
        ]
      },
      {
        path: '/Channel',
        meta: {
          title: 'Channel'
        },
        children: [
          {
            name: 'channel-list',
            path: '',
            component: () => import('@/pages/channel/Index.vue')
          },
          {
            path: ':topic/:msgType',
            name: 'channel-detail',
            meta: {
              title: 'Channel Detail',
              menuKey: '/channel'
            },
            component: () => import('@/pages/channel/Detail.vue')
          }
        ]
      }
    ]
  }
];

export const router = createRouter({
  history: createWebHistory(import.meta.env.VITE_APP_BASE_PATH),
  routes,
  scrollBehavior() {
    return { top: 0 };
  }
});
