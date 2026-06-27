/**
 * 视频发布校验规则（前端镜像，与 backend/util/video_limits.py 保持一致）
 *
 * 修改时请同步更新后端文件。
 */

const KB = 1024
const MB = 1024 * 1024
const GB = 1024 * 1024 * 1024

export const VIDEO_LIMITS = {
  tencent_video: { minDuration: 5,    maxDuration: 5400,         maxSize: 20 * GB, maxTitleLength: 80 },
  iqiyi:         { minDuration: 5,    maxDuration: 3600,         maxSize: 16 * GB, maxTitleLength: Infinity },
  douyin:        { minDuration: 5,    maxDuration: 3600,         maxSize: 16 * GB, maxTitleLength: Infinity },
  baijiahao:     { minDuration: 5,    maxDuration: Infinity,     maxSize: 12 * GB, maxTitleLength: Infinity },
  weibo:         { minDuration: 0,    maxDuration: Infinity,     maxSize: 15 * GB, maxTitleLength: Infinity },
  kuaishou:      { minDuration: 5,    maxDuration: 3600,         maxSize: 12 * GB, maxTitleLength: Infinity },
  bilibili:      { minDuration: 5,    maxDuration: 36000,        maxSize: 16 * GB, maxTitleLength: 80, maxDescLength: 2000 },
  xiaohongshu:   { minDuration: 5,    maxDuration: 14400,        maxSize: 20 * GB, maxTitleLength: 20 },
  channels:      { minDuration: 5,    maxDuration: 28800,        maxSize: 20 * GB, maxTitleLength: Infinity },
  tiktok:        { minDuration: 5,    maxDuration: 3600,         maxSize: 16 * GB, maxTitleLength: Infinity },
  youtube:       { minDuration: 5,    maxDuration: 36000,        maxSize: 16 * GB, maxTitleLength: Infinity },
  alipay:        { minDuration: 5,    maxDuration: Infinity,     maxSize: 8 * GB,  maxTitleLength: Infinity },   // 文档:≤8G,时长不限
  zhihu:         { minDuration: 0,    maxDuration: Infinity,     maxSize: Infinity, maxTitleLength: Infinity }, // 文档:时长大小不限
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
  alipay: '支付宝',
  zhihu: '知乎',
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

/**
 * 按平台规则计算字符数：BMP 字符 = 1，emoji 等非 BMP 字符 = 3。
 * 用于标题/描述长度校验。JS 字符串的 .length 是 UTF-16 单元数（emoji 是 2），
 * 也不能直接用 codepoint 数（emoji 是 1），所以用遍历算。
 */
function countCharsWithEmoji(s) {
  if (!s) return 0
  let n = 0
  for (const ch of s) {
    n += ch.codePointAt(0) > 0xFFFF ? 3 : 1
  }
  return n
}

/**
 * 校验标题是否符合平台限制
 * @param {string} platformKey
 * @param {string} title
 * @returns {{ ok: boolean, error: string, maxLength: number, actualLength: number }}
 */
export function validateTitleForPlatform(platformKey, title) {
  const limits = VIDEO_LIMITS[platformKey]
  if (!limits) return { ok: true, error: '', maxLength: Infinity, actualLength: 0 }
  const name = PLATFORM_NAMES[platformKey] || platformKey
  const max = limits.maxTitleLength
  const len = countCharsWithEmoji(title)
  if (max === Infinity) return { ok: true, error: '', maxLength: Infinity, actualLength: len }
  if (len > max) {
    return {
      ok: false,
      maxLength: max,
      actualLength: len,
      error: `${name}：标题 ${len} 字超过限制 (最多 ${max} 字,emoji 按 3 算)`,
    }
  }
  return { ok: true, error: '', maxLength: max, actualLength: len }
}

/**
 * 校验简介是否符合平台限制（如 B 站 ≤ 2000 字，emoji 按 3 算）
 * @param {string} platformKey
 * @param {string} desc
 * @returns {{ ok: boolean, error: string, maxLength: number, actualLength: number }}
 */
export function validateDescForPlatform(platformKey, desc) {
  const limits = VIDEO_LIMITS[platformKey]
  if (!limits || !limits.maxDescLength) return { ok: true, error: '', maxLength: Infinity, actualLength: 0 }
  const name = PLATFORM_NAMES[platformKey] || platformKey
  const max = limits.maxDescLength
  const len = countCharsWithEmoji(desc)
  if (max === Infinity) return { ok: true, error: '', maxLength: Infinity, actualLength: len }
  if (len > max) {
    return {
      ok: false,
      maxLength: max,
      actualLength: len,
      error: `${name}：简介 ${len} 字超过限制 (最多 ${max} 字,emoji 按 3 算)`,
    }
  }
  return { ok: true, error: '', maxLength: max, actualLength: len }
}
