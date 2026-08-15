<template>
  <div
    class="jd-product-card"
    :class="{ selected }"
    @click="$emit('click')"
  >
    <img v-if="item.image" :src="item.image" :alt="item.title" />
    <div class="jd-product-card-title">{{ item.title }}</div>
    <div v-if="item.price" class="jd-product-card-price">{{ item.price }}</div>
    <div v-if="item.shop_name" class="jd-product-card-shop">{{ item.shop_name }}</div>
    <div class="jd-product-card-check">
      <el-icon v-if="selected"><Check /></el-icon>
    </div>
  </div>
</template>

<script setup>
import { Check } from '@element-plus/icons-vue'

defineProps({
  item: { type: Object, required: true },
  selected: Boolean,
})

defineEmits(['click'])
</script>

<style scoped>
.jd-product-card {
  position: relative;
  padding: 8px;
  border: 2px solid #eee;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}
.jd-product-card:hover {
  border-color: #409eff;
}
.jd-product-card.selected {
  border-color: #67c23a;
  background: #f0f9ff;
}
.jd-product-card img {
  width: 100%;
  height: 120px;
  object-fit: cover;
}
.jd-product-card-title {
  font-size: 13px;
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.jd-product-card-price {
  color: #e1251b;
  font-size: 14px;
  font-weight: bold;
  margin-top: 4px;
}
.jd-product-card-shop {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}
.jd-product-card-check {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  background: #67c23a;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>