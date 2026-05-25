import { http } from '@/utils/request'

export const frameApi = {
  /** Trigger async frame extraction for a video */
  extractFrames(videoPath) {
    return http.post('/api/extract-frames', { video_path: videoPath })
  },

  /** Query extraction progress */
  getFramesStatus(videoPath) {
    return http.get('/api/frames-status', { params: { video_path: videoPath } })
  },

  /** Get list of extracted frames for timeline / recommended frames */
  getFrames(videoPath) {
    return http.get('/api/frames', { params: { video_path: videoPath } })
  },

  /** Get URL for a specific frame image (thumbnail or HD) */
  getFrameImageUrl(videoPath, seconds, thumbnail = false) {
    return `/api/frame-image?video_path=${encodeURIComponent(videoPath)}&seconds=${seconds}&thumbnail=${thumbnail ? '1' : '0'}`
  },
}
