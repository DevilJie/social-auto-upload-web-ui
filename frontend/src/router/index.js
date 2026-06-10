import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import AccountManagement from '../views/AccountManagement.vue'
import MaterialManagement from '../views/MaterialManagement.vue'
import PublishCenter from '../views/PublishCenter.vue'
import PublishHistory from '../views/PublishHistory.vue'
import Settings from '../views/Settings.vue'
import Author from '../views/Author.vue'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard, meta: { icon: 'HomeFilled', title: '仪表盘' } },
  { path: '/account-management', name: 'AccountManagement', component: AccountManagement, meta: { icon: 'User', title: '账号管理' } },
  { path: '/material-management', name: 'MaterialManagement', component: MaterialManagement, meta: { icon: 'Picture', title: '素材管理' } },
  { path: '/drafts', name: 'DraftBox', component: () => import('../views/DraftBox.vue'), meta: { icon: 'Document', title: '草稿箱' } },
  { path: '/publish-center', name: 'PublishCenter', component: PublishCenter, meta: { icon: 'Upload', title: '视频发布' } },
  { path: '/image-publish', name: 'ImagePublish', component: () => import('../views/ImagePublish.vue'), meta: { icon: 'Picture', title: '图文发布' } },
  { path: '/publish-history', name: 'PublishHistory', component: PublishHistory, meta: { icon: 'Clock', title: '发布历史' } },
  { path: '/publish-history/:batchId', name: 'PublishHistoryDetail', component: () => import('../views/PublishHistoryDetail.vue') },
  { path: '/changelog', name: 'Changelog', component: () => import('../views/Changelog.vue'), meta: { icon: 'Notebook', title: '更新日志' } },
  { path: '/settings', name: 'Settings', component: Settings, meta: { icon: 'Setting', title: '系统设置', isBottom: true } },
  { path: '/author', name: 'Author', component: Author, meta: { icon: 'UserFilled', title: '关于作者', isBottom: true } },
  { path: '/feedback', name: 'Feedback', component: () => import('../views/Feedback.vue'), meta: { icon: 'ChatDotRound', title: '一键反馈' } }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router