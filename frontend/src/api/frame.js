import { http } from '@/utils/request'

export const frameApi = {
  /** Trigger async frame extraction for a video */
  extractFrames(materialId) {
    return http.post('/api/extract-frames', { material_id: materialId })
  },

  /** Query extraction progress */
  getFramesStatus(materialId) {
    return http.get('/api/frames-status', { material_id: materialId })
  },

  /** Get list of extracted frames for timeline / recommended frames */
  getFrames(materialId) {
    return http.get('/api/frames', { material_id: materialId })
  },

  /** Get URL for a specific frame image (thumbnail or HD) */
  getFrameImageUrl(materialId, seconds, thumbnail = false) {
    return `/api/frame-image?material_id=${encodeURIComponent(materialId)}&seconds=${seconds}&thumbnail=${thumbnail ? '1' : '0'}`
  },
}
