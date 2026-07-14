<template>
  <div class="channel-summary">
    <div
      class="channels-track"
      :class="{ 'channels-marquee': isOverflow }"
      :ref="el => setRef(el)"
    >
      <span v-for="ch in channels" :key="ch.platform" class="channel-tag">
        <img v-if="ch.logo" :src="ch.logo" class="channel-icon" :alt="ch.name" />
        <span>{{ ch.name }} × {{ ch.count }}</span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'

const props = defineProps({
  channels: { type: Array, required: true },
  overflowKey: { type: [String, Number], default: '' },
})

const trackEl = ref(null)
const isOverflow = ref(false)

function setRef(el) {
  if (el) trackEl.value = el
}

function checkOverflow() {
  if (!trackEl.value) return
  isOverflow.value = trackEl.value.scrollWidth > trackEl.value.parentElement.clientWidth
}

watch(
  () => [props.channels, props.overflowKey],
  () => {
    nextTick(checkOverflow)
  },
  { immediate: true, deep: true }
)
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.channel-summary {
  overflow: hidden;
}

.channels-track {
  display: inline-flex;
  gap: 6px;
  white-space: nowrap;
}

.channels-marquee {
  animation: channels-marquee 8s linear infinite;
}

.channel-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  line-height: 1.4;
  color: $text-secondary;
  background: rgba($overlay-rgb, 0.06);
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
  border: 1px solid $border-light;
  transition: background $transition-base, color $transition-base, border-color $transition-base, transform $transition-base;

  &:hover {
    background: rgba($brand-start, 0.12);
    color: $text-primary;
    border-color: $border-active;
    transform: translateY(-1px);
  }
}

.channel-icon {
  width: 14px;
  height: 14px;
  border-radius: 2px;
  object-fit: contain;
}

@keyframes channels-marquee {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

@media (prefers-reduced-motion: reduce) {
  .channels-marquee {
    animation: none;
  }
  .channel-tag {
    transition: none;
    &:hover {
      transform: none;
    }
  }
}
</style>
