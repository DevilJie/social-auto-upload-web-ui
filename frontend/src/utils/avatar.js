/**
 * 头像相关工具
 */

/** 默认头像:首字母 + ui-avatars 随机色背景 */
export function getDefaultAvatar(name) {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=random`
}

/**
 * 头像代理:绕过 sinaimg.cn 防盗链
 * 把微博/新浪系头像 URL 走本后端 /api/image-proxy 转发
 */
export function proxyAvatar(url) {
  const api = window.__AVATAR_PROXY_API__ || '/api/image-proxy'
  return url && url.includes('sinaimg.cn') ? `${api}?url=${encodeURIComponent(url)}` : url
}