<template>
  <div class="video-queue-bar">
    <div class="vq-header">
      <span class="vq-title">视频队列</span>
      <span class="vq-summary">
        共 {{ videos.length }} 个视频 · 已选账号合计 {{ totalAccounts }} 个
      </span>
    </div>
    <div class="vq-scroll">
      <div
        v-for="(v, i) in videos"
        :key="i"
        :class="['vq-card', { active: i === current }]"
        @click="$emit('select', i)"
      >
        <div class="vq-thumb">
          <img v-if="v.coverUrl" :src="v.coverUrl" loading="lazy" alt="" />
          <div v-else class="vq-thumb-empty">
            <el-icon :size="18"><VideoCameraFilled /></el-icon>
          </div>
          <span v-if="!v.hasVideo" class="vq-badge vq-badge--danger">未上传</span>
          <span v-else-if="v.warn" class="vq-badge vq-badge--warn">待完善</span>
          <button
            v-if="videos.length > 1"
            class="vq-remove"
            title="移除该视频"
            @click.stop="$emit('remove', i)"
          >
            <el-icon :size="12"><Close /></el-icon>
          </button>
          <span v-if="i === current" class="vq-current-tag">编辑中</span>
        </div>
        <div class="vq-name" :title="v.name">{{ v.name }}</div>
        <div class="vq-meta">
          <span>{{ v.accountCount }} 账号</span>
          <span v-if="v.hasSchedule" class="vq-meta-schedule">定时</span>
        </div>
      </div>

      <el-dropdown
        class="vq-add-dropdown"
        trigger="click"
        placement="bottom-start"
        @command="(cmd) => $emit('add', cmd)"
      >
        <div class="vq-card vq-card--add">
          <div class="vq-add-icon">
            <el-icon :size="22"><Plus /></el-icon>
            <span>添加视频</span>
          </div>
          <div class="vq-name vq-name--add">素材库 / 本地上传</div>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="library">
              <el-icon><FolderOpened /></el-icon>
              从素材库选择
            </el-dropdown-item>
            <el-dropdown-item command="upload">
              <el-icon><UploadFilled /></el-icon>
              本地上传
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Plus, Close, VideoCameraFilled, FolderOpened, UploadFilled } from '@element-plus/icons-vue'

const props = defineProps({
  videos: { type: Array, default: () => [] },  // [{name, coverUrl, accountCount, hasVideo, warn, hasSchedule}]
  current: { type: Number, default: 0 },
})

defineEmits(['select', 'add', 'remove'])

const totalAccounts = computed(() =>
  props.videos.reduce((sum, v) => sum + (v.accountCount || 0), 0)
)
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.video-queue-bar {
  flex-shrink: 0;
  padding: 10px 24px;
  border-bottom: 1px solid $border;
  background: $bg-elevated;

  .vq-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;

    .vq-title {
      font-size: 13px;
      font-weight: 600;
      color: $text-primary;
    }
    .vq-summary {
      font-size: 12px;
      color: $text-muted;
    }
  }

  .vq-scroll {
    display: flex;
    gap: 10px;
    overflow-x: auto;
    padding-bottom: 2px;

    &::-webkit-scrollbar {
      height: 4px;
    }
    &::-webkit-scrollbar-thumb {
      background: rgba($overlay-rgb, 0.15);
      border-radius: 2px;
    }
  }

  // 添加卡片外层 dropdown 包装（inline span），保持 flex 布局不塌
  .vq-add-dropdown {
    flex-shrink: 0;
    display: inline-flex;
  }

  .vq-card {
    flex-shrink: 0;
    width: 128px;
    border: 2px solid transparent;
    border-radius: 8px;
    padding: 4px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;

    &:hover {
      background: rgba($overlay-rgb, 0.04);
    }
    &.active {
      border-color: $brand-start;
    }

    .vq-thumb {
      position: relative;
      width: 100%;
      aspect-ratio: 16 / 9;
      border-radius: 6px;
      overflow: hidden;
      background: rgba($overlay-rgb, 0.06);

      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }

      .vq-thumb-empty {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: $text-muted;
      }

      .vq-badge {
        position: absolute;
        top: 4px;
        left: 4px;
        font-size: 10px;
        padding: 1px 5px;
        border-radius: 3px;
        color: #fff;

        &.vq-badge--danger { background: $danger-color; }
        &.vq-badge--warn { background: $warning-color; }
      }

      .vq-remove {
        position: absolute;
        top: 3px;
        right: 3px;
        width: 18px;
        height: 18px;
        display: none;
        align-items: center;
        justify-content: center;
        border: none;
        border-radius: 50%;
        background: rgba(0, 0, 0, 0.55);
        color: #fff;
        cursor: pointer;
        padding: 0;
      }
      &:hover .vq-remove {
        display: flex;
      }

      .vq-current-tag {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        font-size: 10px;
        text-align: center;
        padding: 1px 0;
        color: #fff;
        background: rgba($brand-start, 0.85);
      }
    }

    .vq-name {
      margin-top: 4px;
      font-size: 12px;
      color: $text-primary;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;

      &.vq-name--add {
        color: $text-muted;
        font-size: 11px;
      }
    }

    .vq-meta {
      display: flex;
      gap: 6px;
      font-size: 11px;
      color: $text-muted;

      .vq-meta-schedule {
        color: $warning-color;
      }
    }

    &.vq-card--add {
      display: flex;
      flex-direction: column;
      justify-content: center;
      border: 2px dashed rgba($overlay-rgb, 0.2);
      width: 128px;
      min-height: 88px;

      .vq-add-icon {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
        color: $text-secondary;
        font-size: 12px;
      }
      &:hover {
        border-color: $brand-start;
        color: $brand-start;

        .vq-add-icon { color: $brand-start; }
      }
    }
  }
}
</style>
