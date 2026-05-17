<template>
  <div class="author-page-c">
    <!-- Star field background -->
    <div class="stars" ref="starsRef"></div>
    <div class="center-glow"></div>

    <div class="container">
      <!-- Header Badge -->
      <div class="header-badge">
        <span class="pulse">●</span> 正在播放: 程序员老蔡的故事
      </div>

      <!-- Avatar Section -->
      <div class="avatar-section">
        <div class="avatar-orbit">
          <div class="orbit-ring outer"><div class="orbit-dot"></div></div>
          <div class="orbit-ring inner"><div class="orbit-dot"></div></div>
          <div class="avatar-core">
            <img :src="authorInfo.avatar" :alt="authorInfo.name">
          </div>
        </div>
        <h1 class="avatar-name">{{ authorInfo.name }}</h1>
        <p class="avatar-title">{{ authorInfo.tagline }}</p>
        <span class="avatar-tagline">10年+ 技术沉淀，持续拥抱变化</span>
      </div>

      <!-- Links Grid -->
      <div class="links-orbit">
        <a class="link-card" v-for="project in authorInfo.projects" :key="project.name"
           :href="project.url" target="_blank" rel="noopener">
          <div class="link-icon" :style="{ background: project.gradient }">
            <component :is="project.icon" />
          </div>
          <div class="link-title">{{ project.name }}</div>
          <div class="link-desc">{{ project.desc }}</div>
          <div class="link-url">{{ project.url.replace('https://', '') }} →</div>
        </a>
      </div>

      <!-- Bio Section -->
      <div class="bio-section">
        <h2>关于我</h2>
        <p class="bio-text">
          从 <span class="highlight">Java 后端</span>起步，10年摸爬滚打让我理解了什么是好的架构与代码。
          但我厌倦了只躲在服务器后面，于是主动拥抱前端，从 Vue 到 React，从写页面到理解用户。
          <br><br>
          AI 浪潮来袭，我选择站在浪尖——用 AI 重塑生产力。<span class="highlight">社交媒体自动上传工具</span>就是我的答案，
          让创作者专注内容，把发布交给代码。
          <br><br>
          <span class="highlight">相信工具改变效率，代码改变世界。</span>
        </p>
      </div>

      <!-- Skills Strip -->
      <div class="skills-strip">
        <span class="skill-badge" v-for="skill in authorInfo.skills" :key="skill">{{ skill }}</span>
      </div>

      <!-- Bottom Section -->
      <div class="bottom-section">
        <div class="qr-box">
          <div class="qr-img">
            <img :src="authorInfo.wechatQr" alt="微信二维码">
            <div class="qr-zoom">
              <img :src="authorInfo.bigQrcode" alt="微信二维码">
            </div>
          </div>
          <p class="qr-label">微信扫码联系</p>
        </div>

        <div class="cta-text">
          <h3>让我们连接</h3>
          <p>无论是技术交流还是项目合作</p>
        </div>

        <div class="social-links">
          <a class="social-btn" href="https://github.com/DevilJie" target="_blank" rel="noopener">
            <component :is="GithubIcon" />
            GitHub
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import headImg from '@/assets/head.png'
import qrcodeImg from '@/assets/qrcode.png'
import bigQrcodeImg from '@/assets/big_qrcode.jpg'

const BlogIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
      h('path', { d: 'M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z' })
    ])
  }
}

const AiIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' }, [
      h('path', { d: 'M12 2a10 10 0 1 0 10 10H12V2zM12 2a10 10 0 0 1 10 10' })
    ])
  }
}

const GithubIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'currentColor' }, [
      h('path', { d: 'M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z' })
    ])
  }
}

const authorInfo = {
  name: '程序员老蔡',
  avatar: headImg,
  tagline: '全栈工程师 · AI 探索者 · 效率工具研究者',
  skills: ['Java', 'Spring Boot', 'Vue.js', 'React', 'Python', 'Flask', 'Playwright', 'AI 集成', '自动化'],
  wechatQr: qrcodeImg,
  bigQrcode: bigQrcodeImg,
  projects: [
    {
      name: '个人博客',
      desc: '技术分享、踩坑记录与成长思考',
      url: 'https://blog.cjxch.com',
      icon: BlogIcon,
      gradient: 'linear-gradient(135deg, #8b5cf6, #3b82f6)'
    },
    {
      name: 'AI 创作工厂',
      desc: '一站式 AI 内容创作平台',
      url: 'https://ai.cjxch.com',
      icon: AiIcon,
      gradient: 'linear-gradient(135deg, #06b6d4, #22c55e)'
    },
    {
      name: 'GitHub',
      desc: '开源项目与代码实践',
      url: 'https://github.com/DevilJie',
      icon: GithubIcon,
      gradient: 'linear-gradient(135deg, #333, #24292e)'
    }
  ]
}

const starsRef = ref(null)

onMounted(() => {
  if (starsRef.value) {
    for (let i = 0; i < 100; i++) {
      const star = document.createElement('div')
      star.className = 'star'
      star.style.left = Math.random() * 100 + '%'
      star.style.top = Math.random() * 100 + '%'
      star.style.animationDelay = Math.random() * 3 + 's'
      star.style.width = (Math.random() * 2 + 1) + 'px'
      star.style.height = star.style.width
      starsRef.value.appendChild(star)
    }
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.author-page-c {
  min-height: 100vh;
  overflow-x: hidden;
  position: relative;
}

// Star field
.stars {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}

.star {
  position: absolute;
  width: 2px;
  height: 2px;
  background: white;
  border-radius: 50%;
  opacity: 0.3;
  animation: twinkle 3s infinite ease-in-out;
}

@keyframes twinkle {
  0%, 100% { opacity: 0.2; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.2); }
}

.center-glow {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba($brand-start, 0.15) 0%, transparent 60%);
  pointer-events: none;
  z-index: 0;
}

.container {
  position: relative;
  z-index: 1;
  max-width: 1100px;
  margin: 0 auto;
  padding: 60px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.header-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 20px;
  background: $bg-elevated;
  border: 1px solid $border;
  font-size: 13px;
  color: $text-secondary;
  margin-bottom: 60px;

  .pulse {
    color: $brand-start;
    animation: pulse 2s infinite;
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

// Avatar Section
.avatar-section {
  text-align: center;
  margin-bottom: 60px;
}

.avatar-orbit {
  position: relative;
  width: 200px;
  height: 200px;
  margin: 0 auto 30px;
}

.avatar-core {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 120px;
  height: 120px;
  border-radius: 50%;
  overflow: hidden;
  border: 3px solid transparent;
  background: linear-gradient($bg-base, $bg-base) padding-box,
              linear-gradient(135deg, $brand-start, $brand-end, $accent-cyan) border-box;
  z-index: 2;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}

.orbit-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  border: 1px dashed rgba($brand-start, 0.3);
  animation: rotate 30s linear infinite;

  &.outer {
    width: 200px;
    height: 200px;
    animation-duration: 40s;
  }

  &.inner {
    width: 160px;
    height: 160px;
    animation-duration: 25s;
    animation-direction: reverse;
  }
}

.orbit-dot {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: $brand-start;
  box-shadow: 0 0 10px $brand-start;
}

.orbit-ring.outer .orbit-dot {
  top: 0;
  left: 50%;
  transform: translate(-50%, -50%);
}

.orbit-ring.inner .orbit-dot {
  bottom: 0;
  left: 50%;
  transform: translate(-50%, 50%);
  background: $accent-cyan;
  box-shadow: 0 0 10px $accent-cyan;
}

@keyframes rotate {
  from { transform: translate(-50%, -50%) rotate(0deg); }
  to { transform: translate(-50%, -50%) rotate(360deg); }
}

.avatar-name {
  font-size: 36px;
  font-weight: 700;
  background: $gradient-brand;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 8px;
}

.avatar-title {
  font-size: 16px;
  color: $text-secondary;
  margin-bottom: 16px;
}

.avatar-tagline {
  display: inline-flex;
  padding: 6px 16px;
  border-radius: 20px;
  background: $bg-surface;
  border: 1px solid $border;
  font-size: 13px;
  color: $text-muted;
}

// Links Grid
.links-orbit {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  width: 100%;
  max-width: 900px;
  margin-bottom: 60px;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

.link-card {
  padding: 28px;
  border-radius: 16px;
  background: $bg-elevated;
  border: 1px solid $border;
  text-decoration: none;
  color: inherit;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, $brand-start, $brand-end);
    transform: scaleX(0);
    transition: transform 0.3s ease;
  }

  &:hover::before {
    transform: scaleX(1);
  }

  &:hover {
    border-color: rgba($brand-start, 0.4);
    transform: translateY(-4px);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
  }
}

.link-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;

  :deep(svg) {
    width: 24px;
    height: 24px;
    color: white;
  }
}

.link-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
  color: $text-primary;
}

.link-desc {
  font-size: 13px;
  color: $text-muted;
  margin-bottom: 16px;
}

.link-url {
  font-size: 12px;
  color: $brand-start;
  font-family: monospace;
}

// Bio Section
.bio-section {
  width: 100%;
  max-width: 700px;
  text-align: center;
  padding: 40px;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba($brand-start, 0.08), rgba($brand-end, 0.05));
  border: 1px solid rgba($brand-start, 0.2);
  margin-bottom: 60px;

  h2 {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 20px;
    color: $text-primary;
  }
}

.bio-text {
  font-size: 15px;
  color: $text-secondary;
  line-height: 1.8;
  text-align: left;

  .highlight {
    color: $text-primary;
    font-weight: 500;
  }
}

// Skills Strip
.skills-strip {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 60px;
  width: 100%;
}

.skill-badge {
  padding: 8px 16px;
  border-radius: 20px;
  background: $bg-elevated;
  border: 1px solid $border;
  font-size: 13px;
  color: $text-secondary;
  transition: all 0.2s ease;
  cursor: default;

  &:hover {
    border-color: $brand-start;
    color: $text-primary;
  }
}

// Bottom Section
.bottom-section {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 40px;
  width: 100%;
  padding-top: 40px;
  border-top: 1px solid $border;

  @media (max-width: 768px) {
    flex-direction: column;
    gap: 24px;
  }
}

.qr-box {
  text-align: center;
}

.qr-img {
  width: 90px;
  height: 90px;
  border-radius: 8px;
  background: white;
  padding: 6px;
  margin-bottom: 8px;
  position: relative;
  cursor: pointer;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .qr-zoom {
    position: absolute;
    top: -160px;
    left: 90px;
    width: 200px;
    height: auto;
    border-radius: 12px;
    background: white;
    padding: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    opacity: 0;
    transform: scale(0.8);
    transition: all 0.2s ease;
    pointer-events: none;
    z-index: 10;

    img {
      display: block;
      width: 200px;
      height: auto;
    }
  }

  &:hover .qr-zoom {
    opacity: 1;
    transform: scale(1);
  }
}

.qr-label {
  font-size: 11px;
  color: $text-muted;
}

.cta-text {
  text-align: left;

  h3 {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 6px;
  }

  p {
    font-size: 13px;
    color: $text-muted;
  }
}

.social-links {
  display: flex;
  gap: 12px;
}

.social-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 12px;
  background: $bg-elevated;
  border: 1px solid $border;
  color: $text-primary;
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s ease;

  &:hover {
    border-color: $brand-start;
    background: rgba($brand-start, 0.1);
  }

  :deep(svg) {
    width: 18px;
    height: 18px;
  }
}
</style>