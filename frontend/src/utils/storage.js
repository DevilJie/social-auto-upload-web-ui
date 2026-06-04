const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

/**
 * 统一文件 URL 构建
 * @param {string} storedPath - 相对路径，如 "materials/2026/05/31/uuid.jpg"
 */
export function getFileUrl(storedPath) {
  if (!storedPath) return ''
  if (storedPath.startsWith('http')) return storedPath
  return `${BASE_URL}/api/materials/file/${storedPath}`
}
