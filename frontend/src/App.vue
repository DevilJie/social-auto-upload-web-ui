<template>
  <div class="layout">
    <!-- Icon Rail -->
    <div class="icon-rail">
      <div class="rail-top">
        <div class="logo">S</div>
      </div>

      <div class="rail-nav">
        <el-tooltip
          v-for="item in navItems"
          :key="item.path"
          :content="item.title"
          effect="dark"
          placement="right"
        >
          <div
            class="nav-item"
            :class="{ active: activeMenu === item.path }"
            @click="router.push(item.path)"
          >
            <el-icon :size="20"><component :is="item.icon" /></el-icon>
          </div>
        </el-tooltip>
      </div>

      <div class="rail-separator"></div>

      <div class="rail-bottom">
        <el-tooltip :content="settingsItem.title" effect="dark" placement="right">
          <div
            class="nav-item"
            :class="{ active: activeMenu === settingsItem.path }"
            @click="router.push(settingsItem.path)"
          >
            <el-icon :size="20"><component :is="settingsItem.icon" /></el-icon>
          </div>
        </el-tooltip>
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
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  HomeFilled, User, Picture, Upload,
  List, Clock, Setting
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const iconMap = { HomeFilled, User, Picture, Upload, List, Clock, Setting }

const navItems = [
  { path: '/', icon: HomeFilled, title: '仪表盘' },
  { path: '/account-management', icon: User, title: '账号管理' },
  { path: '/material-management', icon: Picture, title: '素材管理' },
  { path: '/publish-center', icon: Upload, title: '发布中心' },
  { path: '/task-center', icon: List, title: '任务中心' },
  { path: '/publish-history', icon: Clock, title: '发布历史' }
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

// ---- Icon Rail ----
.icon-rail {
  width: 64px;
  background: rgba(255, 255, 255, 0.03);
  border-right: 1px solid $border;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  flex-shrink: 0;

  .rail-top {
    margin-bottom: 16px;

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
    }
  }

  .rail-nav {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    flex: 1;
  }

  .rail-separator {
    height: 1px;
    background: $border;
    margin: 8px 12px;
    width: calc(100% - 24px);
  }

  .rail-bottom {
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

    &:hover {
      background: rgba(255, 255, 255, 0.06);
      color: $text-secondary;
    }

    &.active {
      background: $gradient-brand;
      color: #fff;
    }
  }
}

// ---- Main Area ----
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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

.content {
  flex: 1;
  background: $bg-base;
  padding: 24px;
  overflow-y: auto;
}
</style>
