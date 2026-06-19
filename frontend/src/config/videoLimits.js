/**
 * 视频发布校验规则（前端镜像，与 backend/util/video_limits.py 保持一致）
 *
 * 修改时请同步更新后端文件。
 */

const KB = 1024
const MB = 1024 * 1024
const GB = 1024 * 1024 * 1024

export const VIDEO_LIMITS = {
  tencent_video: { minDuration: 5,    maxDuration: 5400,         maxSize: 20 * GB },
  iqiyi:         { minDuration: 5,    maxDuration: 3600,         maxSize: 16 * GB },
  douyin:        { minDuration: 5,    maxDuration: 3600,         maxSize: 16 * GB },
  baijiahao:     { minDuration: 5,    maxDuration: Infinity,     maxSize: 12 * GB },
  weibo:         { minDuration: 15,   maxDuration: Infinity,     maxSize: 15 * GB },
  kuaishou:      { minDuration: 5,    maxDuration: 3600,         maxSize: 12 * GB },
  bilibili:      { minDuration: 5,    maxDuration: 36000,        maxSize: 16 * GB },
  xiaohongshu:   { minDuration: 5,    maxDuration: 14400,        maxSize: 20 * GB },
  channels:      { minDuration: 5,    maxDuration: 28800,        maxSize: 20 * GB },
  tiktok:        { minDuration: 5,    maxDuration: 3600,         maxSize: 16 * GB },
  youtube:       { minDuration: 5,    maxDuration: 36000,        maxSize: 16 * GB },
}

const PLATFORM_NAMES = {
  tencent_video: '腾讯视频',
  iqiyi: '爱奇艺',
  douyin: '抖音',
  baijiahao: '百家号',
  weibo: '微博',
  kuaishou: '快手',
  bilibili: 'B站',
  xiaohongshu: '小红书',
  channels: '视频号',
  tiktok: 'TikTok',
  youtube: 'YouTube',
}

export function formatSize(sizeBytes) {
  if (sizeBytes == null) return '-'
  if (!isFinite(sizeBytes) || sizeBytes < 0) return '未知'
  if (sizeBytes < KB) return `${sizeBytes.toFixed(1)} B`
  if (sizeBytes < MB) return `${(sizeBytes / KB).toFixed(1)} KB`
  if (sizeBytes < GB) return `${(sizeBytes / MB).toFixed(1)} MB`
  return `${(sizeBytes / GB).toFixed(1)} GB`
}

export function formatDuration(seconds) {
  if (seconds == null) return '-'
  if (!isFinite(seconds) || seconds < 0) return '未知'
  const s = Math.floor(seconds)
  if (s < 60) return `${s} 秒`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h} 小时 ${m} 分 ${sec} 秒`
  return `${m} 分 ${sec} 秒`
}

function formatMaxDuration(max) {
  return max === Infinity ? '无限制' : formatDuration(max)
}

/**
 * 校验视频是否符合平台限制
 * @param {string} platformKey
 * @param {number} durationSec
 * @param {number} sizeBytes
 * @returns {{ ok: boolean, error: string }}
 */
export function validateVideoForPlatform(platformKey, durationSec, sizeBytes) {
  const limits = VIDEO_LIMITS[platformKey]
  if (!limits) return { ok: true, error: '' }

  const name = PLATFORM_NAMES[platformKey] || platformKey

  if (durationSec != null && durationSec < limits.minDuration) {
    return {
      ok: false,
      error: `${name}：时长 ${formatDuration(durationSec)} 小于最小值 (${formatDuration(limits.minDuration)})`,
    }
  }
  if (durationSec != null && durationSec > limits.maxDuration) {
    return {
      ok: false,
      error: `${name}：时长 ${formatDuration(durationSec)} 超出最大值 (${formatMaxDuration(limits.maxDuration)})`,
    }
  }
  if (sizeBytes != null && sizeBytes > limits.maxSize) {
    return {
      ok: false,
      error: `${name}：大小 ${formatSize(sizeBytes)} 超出限制 (最大 ${formatSize(limits.maxSize)})`,
    }
  }
  return { ok: true, error: '' }
}
