import { ref, onMounted, onBeforeUnmount } from 'vue'

// 每秒跳动的当前时间戳：驱动「距发布还有 mm:ss」倒计时文本刷新。
// 组件挂载期间运行，卸载自动清理。发布历史列表/详情等页面共用。
export function useNowTicker(intervalMs = 1000) {
  const now = ref(Date.now())
  let timer = null
  onMounted(() => {
    timer = setInterval(() => { now.value = Date.now() }, intervalMs)
  })
  onBeforeUnmount(() => {
    if (timer) { clearInterval(timer); timer = null }
  })
  return now
}

// 毫秒 → "mm:ss"（≥1 小时显示 "H:MM:SS"）
export function formatCountdown(ms) {
  const total = Math.ceil(Math.max(0, ms) / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = n => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

// 计算一个批次（batch）的「距发布」剩余毫秒：
// 仅当批次还在 pending 且已被发布链排程（scheduled_at 在未来）时返回数字，
// 否则返回 null（不显示倒计时）。
export function batchCountdownMs(batch, nowMs) {
  if (!batch || batch.status !== 'pending' || !batch.scheduled_at) return null
  const ts = Date.parse(batch.scheduled_at)
  if (Number.isNaN(ts)) return null
  const ms = ts - nowMs
  return ms > 0 ? ms : null
}
