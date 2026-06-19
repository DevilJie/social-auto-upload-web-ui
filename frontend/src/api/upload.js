import { http } from '@/utils/request'

/**
 * 分片上传 API（用于大文件 > 100MB，避免 axios onUploadProgress 在超大 multipart 时不更新）。
 *
 * 流程：init → 并发上传 chunks → merge
 */
export const uploadApi = {
  /**
   * 初始化上传会话
   * @param {Object} data
   * @param {string} data.filename
   * @param {number} data.file_size
   * @param {string} [data.mime_type]
   * @param {number} [data.chunk_size] 单位字节，默认 50MB
   * @returns {Promise<{upload_id, total_chunks, chunk_size, uploaded_chunks: number[]}>}
   */
  init(data) {
    return http.post('/api/uploads/init', data)
  },

  /**
   * 上传单个分片
   * @param {string} upload_id
   * @param {number} chunk_index 0-based
   * @param {Blob} chunkBlob
   * @param {(evt: {loaded, total}) => void} [onProgress] 单片进度回调
   * @returns {Promise<{uploaded_chunks, total_chunks}>}
   */
  uploadChunk(upload_id, chunk_index, chunkBlob, onProgress) {
    const formData = new FormData()
    formData.append('upload_id', upload_id)
    formData.append('chunk_index', String(chunk_index))
    formData.append('file', chunkBlob, `chunk_${chunk_index}`)
    return http.upload('/api/uploads/chunk', formData, onProgress)
  },

  /**
   * 合并所有分片 → 写 materials 表
   * @param {string} upload_id
   * @returns {Promise<{id, original_filename, stored_path, file_type, file_size, ...}>}
   */
  merge(upload_id) {
    return http.post('/api/uploads/merge', { upload_id })
  },

  /**
   * 查询上传状态（断点续传）
   * @param {string} upload_id
   * @returns {Promise<{uploaded_chunks: number[], total_chunks, status, ...}>}
   */
  status(upload_id) {
    return http.get(`/api/uploads/status?upload_id=${encodeURIComponent(upload_id)}`)
  },

  /**
   * 取消上传 + 清理临时分片
   * @param {string} upload_id
   */
  cancel(upload_id) {
    return http.delete(`/api/uploads?upload_id=${encodeURIComponent(upload_id)}`)
  },
}
