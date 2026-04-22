import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

// 用 hash 模式更适合嵌入到 FastAPI 的 /admin-ui/ 路径下，
// 避免刷新时因前端路由 404 需要在后端再配 catch-all。
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '数据概览', icon: 'DataBoard' },
      },
      {
        path: 'pipeline',
        name: 'pipeline',
        component: () => import('@/views/Pipeline.vue'),
        meta: { title: '数据管线', icon: 'Connection' },
      },
      {
        path: 'relics',
        name: 'relics',
        component: () => import('@/views/Relics.vue'),
        meta: { title: '文物数据', icon: 'Collection' },
      },
      {
        path: 'import',
        name: 'import',
        component: () => import('@/views/Import.vue'),
        meta: { title: '批量导入', icon: 'Upload' },
      },
      {
        path: 'audit',
        name: 'audit',
        component: () => import('@/views/Audit.vue'),
        meta: { title: '审计日志', icon: 'Document' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta?.public) {
    // 登录页：已登录则回首页
    if (auth.authed && to.name === 'login') return { path: '/dashboard' };
    return true;
  }
  if (!auth.authed) return { path: '/login', query: { redirect: to.fullPath } };
  return true;
});

router.afterEach((to) => {
  const title = to.meta?.title as string | undefined;
  document.title = title ? `${title} · 文物平台后台` : '文物平台后台';
});

export default router;
