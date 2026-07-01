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
      { path: 'interfaces', name: 'interfaces', component: () => import('../views/Interfaces.vue'), meta: { title: '接口管理', crumb: '接口测试 / 接口定义' } },
      { path: 'cases', name: 'cases', component: () => import('../views/Cases.vue'), meta: { title: '测试用例', crumb: '接口测试 / 用例管理' } },
      { path: 'orchestration', name: 'orchestration', component: () => import('../views/Orchestration.vue'), meta: { title: '场景编排', crumb: '接口测试 / 可视化编排' } },
      { path: 'reports', name: 'reports', component: () => import('../views/Reports.vue'), meta: { title: '测试报告', crumb: '接口测试 / 报告' } },
      { path: 'traffic', name: 'traffic', component: () => import('../views/Traffic.vue'), meta: { title: '流量回放', crumb: '接口测试 / 流量回放' } },
      { path: 'perf', name: 'perf', component: () => import('../views/Perf.vue'), meta: { title: '压测监控', crumb: '运维 / 压测' } },
      { path: 'environments', name: 'environments', component: () => import('../views/Environments.vue'), meta: { title: '环境管理', crumb: '运维 / 环境' } },
      { path: 'regression', name: 'regression', component: () => import('../views/Regression.vue'), meta: { title: '回归执行', crumb: '接口测试 / 回归门禁' } },
      { path: 'mocks', name: 'mocks', component: () => import('../views/Mocks.vue'), meta: { title: 'Mock 挡板', crumb: '运维 / 挡板服务' } },
      { path: 'schedules', name: 'schedules', component: () => import('../views/Schedules.vue'), meta: { title: '定时调度', crumb: '运维 / 定时任务' } },
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
