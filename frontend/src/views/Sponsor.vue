<template>
  <div class="sponsor-page">
    <!-- 顶部彩虹滚动条 -->
    <div class="rainbow-bar"></div>

    <!-- 多色径向光晕背景 -->
    <div class="ambient ambient-1"></div>
    <div class="ambient ambient-2"></div>
    <div class="ambient ambient-3"></div>

    <!-- 装饰小星星 -->
    <div class="stars">
      <span v-for="i in 28" :key="i" class="star" :style="randomStar(i)"></span>
    </div>

    <div class="container">
      <!-- 顶部徽章 -->
      <div class="badge">
        <span class="dot"></span>
        <span>赞助开发者 · 让免费继续</span>
      </div>

      <!-- 大标题 -->
      <h1 class="hero-title">
        <span class="line line-1">支持一个</span>
        <span class="line line-2">
          <span class="grad-text">免费工具</span>的
        </span>
        <span class="line line-3">第 <span class="num">{{ dayCount }}</span> 天</span>
      </h1>

      <!-- 副标题 -->
      <p class="hero-sub">
        ☕ 一杯咖啡，让这个深夜有点甜
      </p>

      <!-- 双二维码大卡片 -->
      <section class="qr-section">
        <div
          v-for="qr in qrcodes"
          :key="qr.name"
          class="qr-card"
          :style="{ '--accent': qr.accent }"
        >
          <div class="qr-card-head">
            <div class="qr-icon" :style="{ background: qr.iconBg }">
              <component :is="qr.icon" />
            </div>
            <div class="qr-name">{{ qr.name }}</div>
            <div class="qr-tag">扫码支持</div>
          </div>
          <div class="qr-img-wrap" @click="openPreview(qr)">
            <img :src="qr.img" :alt="qr.name">
            <div class="qr-img-mask">
              <span>👆 点击放大</span>
            </div>
          </div>
          <div class="qr-card-foot">
            <span class="emoji">{{ qr.emoji }}</span>
            <span>{{ qr.slogan }}</span>
          </div>
        </div>
      </section>

      <!-- 共情文字 -->
      <section class="empathy">
        <p class="lead">
          <span class="heart">♥</span>
          <span class="hl-strong">「一键分发」</span>
          这个核心功能，
          <span class="hl">永久免费，对所有人开放。</span>
        </p>
        <p>
          我知道你看到"赞助"两个字时，大概率想关掉——
          凭什么要给一个素不相识的人打钱？
        </p>
        <p>
          所以下面这段话，是写给愿意停下来的你：
        </p>
        <p class="quote">
          这个项目从第一行代码到现在，不过短短两个月。
          但每一个深夜、每一个周末、每一个节假日，我都在给它多写一点功能。
        </p>
        <p>
          没有团队，没有融资，没有一分钱收入。
          <span class="hl">唯一支撑我继续写下去的，是你——真的在用它的人。</span>
          你的每一次一键发布、每一条反馈、每一个 bug 报告，
          都在告诉我：这件事值得继续。
        </p>
        <p>
          如果你愿意，扫一扫上方的二维码，
          一杯咖啡的钱，让这个深夜不再只有我一个人。
        </p>
        <p class="finale">
          如果不愿意，也没关系——谢谢你愿意把这一页读完，
          这本身，对我来说就已经很珍贵了。🙇
        </p>
      </section>

      <!-- 页脚 -->
      <footer class="footer">
        <div class="footer-line"></div>
        <p>—— 程序员老蔡</p>
        <p class="footer-sub">愿好工具，被温柔以待。</p>
      </footer>
    </div>

    <!-- 大图预览 -->
    <transition name="fade">
      <div v-if="previewQr" class="preview-mask" @click="previewQr = null">
        <div class="preview-box" @click.stop>
          <img :src="previewQr.img" :alt="previewQr.name">
          <p>{{ previewQr.name }} · 长按或截图保存</p>
          <button class="preview-close" @click="previewQr = null">✕</button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, h } from 'vue'
import alipayImg from '@/assets/alipay.jpg'
import weixinImg from '@/assets/weixin.jpg'

const AlipayIcon = {
  render: () => h('svg', { viewBox: '0 0 24 24', fill: 'currentColor' }, [
    h('path', { d: 'M6.68 13.27c-.86.34-1.68.5-2.41.5-.7 0-1.28-.18-1.7-.53-.42-.36-.64-.85-.64-1.45 0-1.42 1.06-2.13 3.18-2.13.46 0 .97.04 1.52.11 0 .86.02 1.78.05 2.74-.05.27-.05.55 0 .76zm.9-3.78c1.36.2 2.85.58 4.42 1.1.78-1.4 1.78-2.7 2.95-3.86-2.6-1.27-5.46-1.74-8.5-1.42C5.18 5.7 4 6.95 3.27 8.36c1.36-.46 2.95-.7 4.31-.87zm5.7 1.66c1.96.78 3.66 1.55 4.74 2.13.42-2.65.04-4.97-1.1-6.95-1.34 1.36-2.6 2.96-3.64 4.82zm-3.5 3.96c-.46 1.85-1.27 3.18-2.42 3.96-.9.62-1.95.93-3.13.93-1.96 0-3.5-.78-4.6-2.34l-.06-.1c1.46 1.2 3.42 1.5 5.45.5 1.27-.62 2.34-1.66 3.2-3.1.34-.57.62-1.13.86-1.7-.5-.18-1-.34-1.5-.5-.7 1.42-1.34 2.34-1.8 2.85zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z' })
  ])
}

const WechatIcon = {
  render: () => h('svg', { viewBox: '0 0 24 24', fill: 'currentColor' }, [
    h('path', { d: 'M8.69 4C4.62 4 1.33 6.72 1.33 10.07c0 1.93 1.1 3.65 2.82 4.78l-.7 2.13 2.48-1.25c.88.24 1.83.42 2.83.42h.5a4.84 4.84 0 0 1-.2-1.37c0-3.1 2.94-5.6 6.56-5.6.2 0 .4 0 .6.03C15.5 6.18 12.36 4 8.69 4zm-2.4 3.1a.86.86 0 1 1 0 1.72.86.86 0 0 1 0-1.72zm4.8 0a.86.86 0 1 1 0 1.72.86.86 0 0 1 0-1.72zm4.5 3.18c-3.07 0-5.56 2.13-5.56 4.76 0 2.63 2.49 4.76 5.56 4.76.66 0 1.3-.1 1.9-.28l1.9.97-.53-1.62c1.4-.93 2.3-2.34 2.3-3.83 0-2.63-2.5-4.76-5.57-4.76zm-1.85 2.2a.7.7 0 1 1 0 1.4.7.7 0 0 1 0-1.4zm3.7 0a.7.7 0 1 1 0 1.4.7.7 0 0 1 0-1.4z' })
  ])
}

const qrcodes = [
  {
    name: '支付宝',
    img: alipayImg,
    accent: '#1677FF',
    iconBg: 'linear-gradient(135deg, #1677FF, #00A6FF)',
    icon: AlipayIcon,
    emoji: '💙',
    slogan: '推荐 · 实时到账'
  },
  {
    name: '微信支付',
    img: weixinImg,
    accent: '#07C160',
    iconBg: 'linear-gradient(135deg, #07C160, #00D26A)',
    icon: WechatIcon,
    emoji: '💚',
    slogan: '扫码即到 · 谢谢支持'
  }
]

// 项目启动日：从这天起开始计时
const PROJECT_START = new Date('2026-05-15T00:00:00')

// 当前时间戳（用于触发响应式更新）
const now = ref(Date.now())

// 第几天：今天 - 启动日 + 1（启动当天算第 1 天）
const dayCount = computed(() => {
  const diff = Math.floor((now.value - PROJECT_START.getTime()) / 86400000) + 1
  return Math.max(1, diff)
})

// 每分钟刷新一次，跨天时自动 +1
let timer = null
onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 60000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

// 装饰星星位置
const randomStar = (i) => {
  const seed = (i * 9301 + 49297) % 233280
  const r = seed / 233280
  const x = ((i * 37) % 100)
  const y = ((i * 53 + 13) % 100)
  const size = 1 + (r * 2)
  const delay = (r * 3).toFixed(2)
  return {
    left: `${x}%`,
    top: `${y}%`,
    width: `${size}px`,
    height: `${size}px`,
    animationDelay: `${delay}s`
  }
}

const previewQr = ref(null)
const openPreview = (qr) => { previewQr.value = qr }
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.sponsor-page {
  min-height: 100vh;
  position: relative;
  overflow-x: hidden;
  background: $bg-base;
}

// ============== 顶部彩虹滚动条 ==============
.rainbow-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(
    90deg,
    $brand-start,
    $brand-end,
    $accent-cyan,
    $accent-green,
    $accent-amber,
    $accent-rose,
    $brand-start
  );
  background-size: 200% 100%;
  animation: rainbow-shift 6s linear infinite;
  z-index: 100;
}

@keyframes rainbow-shift {
  0% { background-position: 0% 0; }
  100% { background-position: 200% 0; }
}

// ============== 多色径向光晕 ==============
.ambient {
  position: fixed;
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
  filter: blur(60px);
}

.ambient-1 {
  top: -150px;
  left: -100px;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba($brand-start, 0.30) 0%, transparent 60%);
}

.ambient-2 {
  top: 30%;
  right: -150px;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba($accent-rose, 0.25) 0%, transparent 60%);
}

.ambient-3 {
  bottom: -100px;
  left: 30%;
  width: 700px;
  height: 700px;
  background: radial-gradient(circle, rgba($accent-cyan, 0.20) 0%, transparent 60%);
}

// 装饰小星星
.stars {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.star {
  position: absolute;
  background: $text-primary;
  border-radius: 50%;
  opacity: 0.35;
  animation: twinkle 3s ease-in-out infinite;
}

@keyframes twinkle {
  0%, 100% { opacity: 0.15; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(1.4); }
}

.container {
  position: relative;
  z-index: 1;
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 24px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

// ============== 顶部徽章 ==============
.badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-radius: 999px;
  background: rgba($bg-elevated-rgb, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid $border;
  font-size: 12px;
  color: $text-secondary;
  letter-spacing: 0.5px;
  margin-bottom: 16px;

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: $accent-rose;
    box-shadow: 0 0 8px $accent-rose;
    animation: heartbeat 1.5s ease-in-out infinite;
  }
}

@keyframes heartbeat {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.4); opacity: 0.6; }
}

// ============== 大标题 ==============
.hero-title {
  text-align: center;
  margin-bottom: 8px;
  line-height: 1.1;
  font-weight: 800;
  letter-spacing: -1px;

  .line {
    display: block;
    font-size: clamp(28px, 4.5vw, 42px);
    color: $text-primary;
  }

  .grad-text {
    background: linear-gradient(
      90deg,
      $brand-start,
      $accent-rose,
      $accent-amber,
      $brand-start
    );
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: text-flow 4s linear infinite;
  }

  .num {
    background: $gradient-brand;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: 900;
    font-size: 1.1em;
  }
}

@keyframes text-flow {
  0% { background-position: 0% center; }
  100% { background-position: 200% center; }
}

.hero-tag {
  font-size: 13px;
  color: $text-muted;
  margin-bottom: 24px;
  text-align: center;
}

// ============== 双二维码卡片 ==============
.qr-section {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  width: 100%;
  margin-bottom: 40px;

  @media (max-width: 600px) {
    grid-template-columns: 1fr;
  }
}

.qr-card {
  padding: 16px 18px 16px;
  border-radius: 16px;
  background: $bg-elevated;
  border: 1px solid $border;
  text-align: center;
  transition: all $transition-base;
  position: relative;
  overflow: hidden;

  // 顶部一道彩色高光
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--accent);
    opacity: 0.7;
  }

  &:hover {
    transform: translateY(-4px);
    border-color: var(--accent);
    box-shadow: 0 16px 32px rgba(0, 0, 0, 0.25), 0 0 0 4px rgba(255, 255, 255, 0.04);
  }
}

.qr-card-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 10px;
}

.qr-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;

  :deep(svg) {
    width: 14px;
    height: 14px;
    color: #fff;
  }
}

.qr-name {
  font-size: 14px;
  font-weight: 700;
  color: $text-primary;
}

.qr-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(var(--accent), 0.15);
  color: var(--accent);
  font-weight: 600;
  letter-spacing: 0.5px;
}

.qr-img-wrap {
  width: 100%;
  max-width: 170px;
  aspect-ratio: 1;
  margin: 0 auto;
  border-radius: 10px;
  background: #fff;
  padding: 8px;
  position: relative;
  cursor: zoom-in;
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 4px;
    transition: transform $transition-base;
  }

  .qr-img-mask {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    opacity: 0;
    transition: opacity $transition-base;
    border-radius: 10px;
  }

  &:hover .qr-img-mask { opacity: 1; }
  &:hover img { transform: scale(1.04); }
}

.qr-card-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 11.5px;
  color: $text-muted;

  .emoji { font-size: 13px; }
}

// ============== 共情文字 ==============
.empathy {
  width: 100%;
  max-width: 600px;
  margin-bottom: 32px;
  padding: 8px 16px;
  text-align: left;

  p {
    font-size: 13.5px;
    line-height: 1.85;
    color: $text-secondary;
    margin-bottom: 12px;

    &:last-child { margin-bottom: 0; }
  }

  .lead {
    font-size: 15px;
    color: $text-primary;
    font-weight: 500;
    line-height: 1.9;
    padding: 12px 16px;
    border-radius: 12px;
    background: linear-gradient(135deg, rgba($accent-rose, 0.08), rgba($brand-start, 0.06));
    border: 1px solid rgba($accent-rose, 0.2);
    margin-bottom: 16px;

    .heart {
      color: $accent-rose;
      display: inline-block;
      margin-right: 4px;
      animation: heartbeat 1.5s ease-in-out infinite;
    }

    .hl-strong {
      background: linear-gradient(135deg, $accent-rose, $brand-start);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-weight: 800;
      font-size: 1.05em;
    }

    .hl {
      color: $accent-amber;
      font-weight: 600;
    }
  }

  .quote {
    position: relative;
    padding: 10px 14px;
    margin: 12px 0;
    border-left: 3px solid $accent-rose;
    background: rgba($accent-rose, 0.05);
    border-radius: 0 8px 8px 0;
    color: $text-primary;
    font-size: 13px;
    line-height: 1.7;
  }

  .hl {
    color: $accent-amber;
    font-weight: 600;
  }

  .finale {
    margin-top: 14px;
    padding: 12px 18px;
    border-radius: 10px;
    background: linear-gradient(135deg, rgba($brand-start, 0.08), rgba($accent-rose, 0.05));
    border: 1px dashed rgba($brand-start, 0.3);
    color: $text-primary;
    text-align: center;
    font-size: 13px;
    line-height: 1.75;
  }
}

// ============== 页脚 ==============
.footer {
  text-align: center;

  .footer-line {
    width: 32px;
    height: 2px;
    background: $gradient-brand;
    margin: 0 auto 10px;
    border-radius: 2px;
  }

  p {
    font-size: 12.5px;
    color: $text-muted;
    line-height: 1.6;
  }
}

// ============== 大图预览 ==============
.preview-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.78);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: $z-overlay;
}

.preview-box {
  position: relative;
  background: #fff;
  padding: 22px 22px 18px;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  text-align: center;

  img {
    width: 300px;
    height: 300px;
    object-fit: cover;
    border-radius: 10px;
    display: block;
  }

  p {
    margin-top: 12px;
    font-size: 13px;
    color: #333;
  }
}

.preview-close {
  position: absolute;
  top: -14px;
  right: -14px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  background: #fff;
  color: #333;
  font-size: 16px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);

  &:hover { background: #f5f5f5; }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 200ms ease;
}
.fade-enter-from,
.fade-leave-to { opacity: 0; }
</style>