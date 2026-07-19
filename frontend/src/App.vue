<template>
  <div class="layout">
    <!-- Sidebar -->
    <div class="sidebar" :class="{ expanded: !sidebarCollapsed }">
      <div class="sidebar-top">
        <div class="logo">S</div>
        <button class="toggle-btn" @click="sidebarCollapsed = !sidebarCollapsed">
          <el-icon :size="16"><component :is="sidebarCollapsed ? Expand : Fold" /></el-icon>
        </button>
      </div>

<div class="sidebar-nav">
        <template v-for="item in navItems" :key="item.title">
          <el-tooltip v-if="sidebarCollapsed" :content="item.title" effect="dark" placement="right">
            <div
              class="nav-item"
              :class="{ active: activeMenu === item.path }"
              @click="router.push(item.path)"
            >
              <el-icon :size="20"><component :is="item.icon" /></el-icon>
            </div>
          </el-tooltip>
          <div
            v-else
            class="nav-item expanded-item"
            :class="{ active: activeMenu === item.path }"
            @click="router.push(item.path)"
          >
            <el-icon :size="20"><component :is="item.icon" /></el-icon>
            <span class="nav-label">{{ item.title }}</span>
          </div>
        </template>
      </div>

      <div class="sidebar-separator"></div>

      <div class="sidebar-bottom">
        <template v-for="item in bottomItems" :key="item.path">
          <!-- 折叠态 -->
          <el-tooltip v-if="sidebarCollapsed" :content="item.title" effect="dark" placement="right">
            <div
              class="nav-item"
              :class="[ item._isSponsor ? 'sponsor-item' : '', { active: activeMenu === item.path } ]"
              @click="router.push(item.path)"
            >
              <el-icon :size="20"><component :is="item.icon" /></el-icon>
              <span v-if="item._isSponsor" class="sponsor-dot"></span>
            </div>
          </el-tooltip>

          <!-- 展开态 -->
          <div
            v-else
            class="nav-item expanded-item"
            :class="[ item._isSponsor ? 'sponsor-item sponsor-item--wide' : '', { active: activeMenu === item.path } ]"
            @click="router.push(item.path)"
          >
            <!-- 左侧品牌竖条 -->
            <span v-if="item._isSponsor" class="sponsor-bar"></span>

            <el-icon :size="item._isSponsor ? 22 : 20"><component :is="item.icon" /></el-icon>
            <span class="nav-label">{{ item.title }}</span>

            <!-- 打赏头像气泡（仅赞助项，展开态） -->
            <div v-if="item._isSponsor" class="sponsor-bubbles">
              <transition name="bubble" mode="out-in">
                <div
                  class="bubble"
                  :key="currentBubbleIndex"
                  :style="{ '--bubble-color': sponsorBubbles[currentBubbleIndex].color }"
                >
                  <div class="bubble-avatar">{{ sponsorBubbles[currentBubbleIndex].name[0] }}</div>
                  <span class="bubble-amt">+¥{{ sponsorBubbles[currentBubbleIndex].amount }}</span>
                </div>
              </transition>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Right area -->
    <div class="main-area">
      <!-- Header -->
      <header class="header">
        <div class="breadcrumb">{{ pageTitle }}</div>
        <div class="header-right">
          <el-tooltip effect="light" :content="appStore.theme === 'dark' ? '切换到亮色' : '切换到暗色'" placement="bottom">
            <button class="theme-toggle" @click="appStore.toggleTheme">
              <el-icon :size="18">
                <component :is="appStore.theme === 'dark' ? Sunny : Moon" />
              </el-icon>
            </button>
          </el-tooltip>
        </div>
      </header>

      <!-- Content -->
      <main class="content">
        <router-view v-slot="{ Component }">
            <component :is="Component" :key="$route.path" />
          </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled, User, Picture, Upload,
  Clock, Setting, Expand, Fold, UserFilled, Document, Notebook, ChatDotRound,
  Sunny, Moon, Coffee
} from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const sidebarCollapsed = ref(false)

// 菜单项数据
const navItems = [
  { path: '/', icon: HomeFilled, title: '仪表盘' },
  { path: '/account-management', icon: User, title: '账号管理' },
  { path: '/material-management', icon: Picture, title: '素材管理' },
  { path: '/publish-center', icon: Upload, title: '视频发布' },
  { path: '/image-publish', icon: Picture, title: '图集发布' },
  { path: '/drafts', icon: Document, title: '草稿箱' },
  { path: '/publish-history', icon: Clock, title: '发布历史' },
  { path: '/changelog', icon: Notebook, title: '更新日志' },
  { path: '/author', icon: UserFilled, title: '关于作者' },
  { path: '/feedback', icon: ChatDotRound, title: '一键反馈' }
]

// 底部区：赞助作者（醒目版）+ 系统设置
const bottomItems = [
  { path: '/sponsor', icon: Coffee, title: '赞助作者', _isSponsor: true },
  { path: '/settings', icon: Setting, title: '系统设置' }
]

// 打赏头像气泡（循环展示，给赞助项制造"有人在打赏"的氛围）
const sponsorBubbles = [
  { name: '小张', amount: 88, color: '#f43f5e' },
  { name: '阿杰', amount: 50, color: '#06b6d4' },
  { name: 'Vivi', amount: 128, color: '#22c55e' },
  { name: '老王', amount: 20, color: '#f59e0b' }
]
const currentBubbleIndex = ref(0)
setInterval(() => {
  currentBubbleIndex.value = (currentBubbleIndex.value + 1) % sponsorBubbles.length
}, 4000)

const activeMenu = computed(() => route.path)

const pageTitle = computed(() => route.meta?.title || '')
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.layout {
  display: flex;
  height: 100vh;
}

// ---- Sidebar ----
.sidebar {
  width: 64px;
  background: rgba($overlay-rgb, 0.03);
  border-right: 1px solid $border;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  flex-shrink: 0;
  transition: width $transition-slow;
  overflow: hidden;

  &.expanded {
    width: 200px;
    align-items: stretch;
    padding: 12px 12px;

    .sidebar-top {
      justify-content: space-between;
      padding-right: 0;
    }

    .sidebar-nav {
      align-items: stretch;
    }

    .nav-item.expanded-item {
      width: 100%;
      justify-content: flex-start;
      padding: 0 12px;

      .nav-label {
        display: inline;
        margin-left: 12px;
      }
    }

    .sidebar-bottom {
      align-items: stretch;
    }

    .sidebar-separator {
      margin: 8px 0;
      width: 100%;
    }
  }

  .sidebar-top {
    display: flex;
    align-items: center;
    margin-bottom: 16px;
    padding-right: 12px;
    gap: 4px;

    .logo {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: $gradient-brand;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 700;
      font-size: 16px;
      flex-shrink: 0;
    }
  }

  .toggle-btn {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: $radius-sm;
    background: transparent;
    color: $text-muted;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: $transition-base;
    flex-shrink: 0;

    &:hover {
      background: rgba($overlay-rgb, 0.06);
      color: $text-secondary;
    }
  }

  .sidebar-nav {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    flex: 1;
  }

  .sidebar-separator {
    height: 1px;
    background: $border;
    margin: 8px 12px;
    width: calc(100% - 24px);
  }

  .sidebar-bottom {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .nav-item {
    width: 40px;
    height: 40px;
    border-radius: $radius-base;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: $transition-base;
    color: $text-muted;
    white-space: nowrap;
    position: relative;

    &:hover {
      background: rgba($overlay-rgb, 0.06);
      color: $text-secondary;
    }

    &.active {
      background: $gradient-brand;
      color: #fff;
    }

    .nav-label {
      display: none;
      font-size: 13px;
      font-weight: 500;
    }
  }

  // ============== 赞助作者 醒目版（A 方案：底部独立） ==============
  .sponsor-item {
    .el-icon {
      color: $accent-rose;
    }

    // 折叠态右上角红点（呼吸）
    .sponsor-dot {
      position: absolute;
      top: 4px;
      right: 4px;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: $accent-rose;
      box-shadow: 0 0 0 2px var(--sidebar-bg, transparent);
      animation: sponsor-pulse 1.8s ease-in-out infinite;
    }

    &:hover .el-icon { color: $brand-start; }
    &.active .el-icon { color: #fff; }
  }

  // 展开态：加重版（更高、更亮、呼吸更强、左侧竖条）
  .sponsor-item--wide {
    height: 46px;
    border-radius: $radius-base;
    background: linear-gradient(135deg, rgba($accent-rose, 0.16), rgba($brand-start, 0.10));
    border: 1px solid rgba($accent-rose, 0.28);
    overflow: visible;
    position: relative;

    // 呼吸光晕
    &::before {
      content: '';
      position: absolute;
      inset: 0;
      border-radius: $radius-base;
      background: linear-gradient(135deg, rgba($accent-rose, 0.18), rgba($brand-start, 0.12));
      animation: sponsor-breathe 1.8s ease-in-out infinite;
      z-index: -1;
    }

    // 左侧品牌竖条
    .sponsor-bar {
      position: absolute;
      left: -1px;
      top: 8px;
      bottom: 8px;
      width: 3px;
      border-radius: 0 3px 3px 0;
      background: $gradient-brand;
      box-shadow: 0 0 8px rgba($accent-rose, 0.6);
    }

    .el-icon {
      background: $gradient-brand;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .nav-label {
      background: $gradient-brand;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 600;
      font-size: 13.5px;
    }

    &:hover {
      background: linear-gradient(135deg, rgba($accent-rose, 0.22), rgba($brand-start, 0.16));
      transform: translateY(-1px);
      box-shadow: 0 6px 16px rgba($accent-rose, 0.15);
    }

    &.active {
      background: $gradient-brand;
      border-color: transparent;
      .nav-label, .el-icon {
        -webkit-text-fill-color: #fff;
        background: none;
      }
    }
  }

  // 打赏头像气泡（仅展开态）
  .sponsor-bubbles {
    margin-left: auto;
    padding-right: 2px;
    position: relative;
    width: 64px;
    height: 22px;
    overflow: visible;
  }

  .bubble {
    display: flex;
    align-items: center;
    gap: 4px;
    height: 22px;
    padding: 0 8px 0 3px;
    border-radius: 11px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.15);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
    position: absolute;
    right: 0;
    top: 0;
    animation: bubble-pop 4s ease-out forwards;
  }

  .bubble-avatar {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--bubble-color);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .bubble-amt {
    font-size: 10.5px;
    font-weight: 600;
    color: var(--bubble-color);
    white-space: nowrap;
  }
}

@keyframes sponsor-pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 2px var(--sidebar-bg, transparent), 0 0 0 0 rgba(244, 63, 94, 0.6);
  }
  50% {
    transform: scale(1.15);
    box-shadow: 0 0 0 2px var(--sidebar-bg, transparent), 0 0 0 6px rgba(244, 63, 94, 0);
  }
}

@keyframes sponsor-breathe {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.9; }
}

// 打赏气泡：向上漂 + 淡入淡出（4s 循环）
@keyframes bubble-pop {
  0% { transform: translateY(8px) scale(0.6); opacity: 0; }
  15% { transform: translateY(0) scale(1); opacity: 1; }
  75% { transform: translateY(-4px) scale(1); opacity: 1; }
  100% { transform: translateY(-12px) scale(0.9); opacity: 0; }
}

// 气泡切换的过渡（备用，setInterval 已经触发 key 切换）
.bubble-enter-active,
.bubble-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.bubble-enter-from {
  opacity: 0;
  transform: translateY(8px) scale(0.8);
}
.bubble-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.8);
}

// ---- Main Area ----
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  .content {
    flex: 1;
    background: $bg-base;
    padding: 0;
    overflow-y: auto;
  }
}

.header {
  height: 48px;
  background: rgba($overlay-rgb, 0.02);
  border-bottom: 1px solid $border;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;

  .breadcrumb {
    color: $text-primary;
    font-size: 15px;
    font-weight: 600;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .theme-toggle {
    width: 32px;
    height: 32px;
    border: none;
    border-radius: $radius-sm;
    background: transparent;
    color: $text-muted;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: $transition-base;

    &:hover {
      background: $overlay-hover;
      color: $text-primary;
    }
  }
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
