import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AppLayout from '../layouts/AppLayout.vue'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: '/interfaces' },
      { path: 'interfaces', name: 'interfaces', component: () => import('../views/Interfaces.vue'), meta: { title: '接口用例', crumb: '接口测试 / 用例管理' } },
      { path: 'reports', name: 'reports', component: () => import('../views/Placeholder.vue'), meta: { title: '测试报告', crumb: '接口测试 / 报告' } },
      { path: 'traffic', name: 'traffic', component: () => import('../views/Placeholder.vue'), meta: { title: '流量回放', crumb: '接口测试 / 流量回放' } },
      { path: 'perf', name: 'perf', component: () => import('../views/Placeholder.vue'), meta: { title: '压测监控', crumb: '运维 / 压测' } },
      { path: 'environments', name: 'environments', component: () => import('../views/Placeholder.vue'), meta: { title: '环境管理', crumb: '运维 / 环境' } },
    ],
  },
]

const router = createRouter({ history: createWebHashHistory(), routes })

// 路由守卫:非 public 页面必须登录
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.token) return { name: 'login' }
  if (to.name === 'login' && auth.token) return { name: 'interfaces' }
})

export default router
