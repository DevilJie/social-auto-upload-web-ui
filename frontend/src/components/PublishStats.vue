<template>
  <div :class="['publish-stats', { 'publish-stats--compact': compact }]">
    <div
      v-for="item in metrics"
      :key="item.key"
      class="stat-item"
      :class="[
        `stat-item--${item.theme}`,
        {
          'stat-item--placeholder': isPlaceholder(item.value),
          'stat-item--compact': compact,
        },
      ]"
    >
      <el-tooltip
        :content="'数据统计功能开发中'"
        placement="top"
        :disabled="false"
      >
        <div :class="['stat-inner', { 'stat-inner--compact': compact }]">
          <el-icon class="stat-icon" :size="compact ? 13 : 16">
            <component :is="item.icon" />
          </el-icon>
          <span class="stat-label">{{ item.label }}</span>
          <span class="stat-value">{{ formatValue(item.value) }}</span>
        </div>
      </el-tooltip>
    </div>
  </div>
</template>

<script setup>
import { VideoPlay, Star, Collection, ChatLineRound } from '@element-plus/icons-vue'

const props = defineProps({
  compact: { type: Boolean, default: false },
  views: { type: [Number, String, null], default: null },
  likes: { type: [Number, String, null], default: null },
  favorites: { type: [Number, String, null], default: null },
  comments: { type: [Number, String, null], default: null },
})

const metrics = [
  { key: 'views', label: '播放', value: props.views, icon: VideoPlay, theme: 'blue' },
  { key: 'likes', label: '点赞', value: props.likes, icon: Star, theme: 'rose' },
  { key: 'favorites', label: '收藏', value: props.favorites, icon: Collection, theme: 'cyan' },
  { key: 'comments', label: '评论', value: props.comments, icon: ChatLineRound, theme: 'green' },
]

function formatValue(v) {
  if (v == null) return '--'
  if (typeof v === 'number') {
    if (v >= 10000) return (v / 10000).toFixed(1) + 'w'
    return v.toLocaleString('zh-CN')
  }
  return v
}

function isPlaceholder(v) {
  return v == null
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;

  &--compact {
    gap: 6px;
  }
}

.stat-item {
  border: 1px solid $border;
  border-radius: $radius-base;
  background: rgba($overlay-rgb, 0.02);
  padding: 12px 14px;
  transition: $transition-base;
  cursor: default;

  &:hover {
    border-color: $border-active;
    background: rgba($overlay-rgb, 0.04);
  }

  &--compact {
    padding: 8px 4px;
    border-color: transparent;
    background: transparent;

    &:hover {
      border-color: $border-light;
      background: rgba($overlay-rgb, 0.02);
    }
  }
}

// 4 个主题色（基于项目已有 platform/accent 调色板，轻量区分）
.stat-item--blue {
  background: linear-gradient(135deg, rgba($platform-channels, 0.08), rgba($overlay-rgb, 0.02));

  .stat-icon {
    color: $platform-channels;
  }

  &.stat-item--compact {
    background: linear-gradient(135deg, rgba($platform-channels, 0.04), rgba($overlay-rgb, 0.01));
  }
}

.stat-item--rose {
  background: linear-gradient(135deg, rgba($accent-rose, 0.08), rgba($overlay-rgb, 0.02));

  .stat-icon {
    color: $accent-rose;
  }

  &.stat-item--compact {
    background: linear-gradient(135deg, rgba($accent-rose, 0.04), rgba($overlay-rgb, 0.01));
  }
}

.stat-item--cyan {
  background: linear-gradient(135deg, rgba($accent-cyan, 0.08), rgba($overlay-rgb, 0.02));

  .stat-icon {
    color: $accent-cyan;
  }

  &.stat-item--compact {
    background: linear-gradient(135deg, rgba($accent-cyan, 0.04), rgba($overlay-rgb, 0.01));
  }
}

.stat-item--green {
  background: linear-gradient(135deg, rgba($accent-green, 0.08), rgba($overlay-rgb, 0.02));

  .stat-icon {
    color: $accent-green;
  }

  &.stat-item--compact {
    background: linear-gradient(135deg, rgba($accent-green, 0.04), rgba($overlay-rgb, 0.01));
  }
}

// null 占位色（统一为 muted；空值时数字/标签同时降到 muted 视觉层级）
.stat-item--placeholder {
  .stat-label {
    color: $text-placeholder;
  }
  .stat-value {
    color: $text-placeholder;
    font-weight: 500;
  }
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 8px;

  &--compact {
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }
}

.stat-icon {
  flex-shrink: 0;

  .stat-item--compact & {
    font-size: 13px;
  }
}

.stat-label {
  font-size: 12px;
  color: $text-muted;
  flex: 1;

  .stat-item--compact & {
    flex: none;
    font-size: 10px;
    line-height: 1.2;
  }
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
  font-variant-numeric: tabular-nums;

  .stat-item--compact & {
    font-size: 12px;
  }
}
</style>
