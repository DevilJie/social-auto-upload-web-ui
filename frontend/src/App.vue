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
        <template v-for="item in navItems" :key="item.path">
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
        <el-tooltip v-if="sidebarCollapsed" :content="settingsItem.title" effect="dark" placement="right">
          <div
            class="nav-item"
            :class="{ active: activeMenu === settingsItem.path }"
            @click="router.push(settingsItem.path)"
          >
            <el-icon :size="20"><component :is="settingsItem.icon" /></el-icon>
          </div>
        </el-tooltip>
        <div
          v-else
          class="nav-item expanded-item"
          :class="{ active: activeMenu === settingsItem.path }"
          @click="router.push(settingsItem.path)"
        >
          <el-icon :size="20"><component :is="settingsItem.icon" /></el-icon>
          <span class="nav-label">{{ settingsItem.title }}</span>
        </div>
      </div>
    </div>

    <!-- Right area -->
    <div class="main-area">
      <!-- Header -->
      <header class="header">
        <div class="breadcrumb">{{ pageTitle }}</div>
        <div class="header-right"></div>
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
  Clock, Setting, Expand, Fold, UserFilled
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const sidebarCollapsed = ref(true)

const navItems = [
  { path: '/', icon: HomeFilled, title: '仪表盘' },
  { path: '/account-management', icon: User, title: '账号管理' },
  { path: '/material-management', icon: Picture, title: '素材管理' },
  { path: '/publish-center', icon: Upload, title: '发布中心' },
  { path: '/publish-history', icon: Clock, title: '发布历史' },
  { path: '/author', icon: UserFilled, title: '关于作者' }
]

const settingsItem = { path: '/settings', icon: Setting, title: '系统设置' }

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
  background: rgba(255, 255, 255, 0.03);
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
      background: rgba(255, 255, 255, 0.06);
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

    &:hover {
      background: rgba(255, 255, 255, 0.06);
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
  background: rgba(255, 255, 255, 0.02);
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
    // placeholder for future user area
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
