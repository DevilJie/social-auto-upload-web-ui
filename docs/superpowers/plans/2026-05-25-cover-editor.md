# Cover Editor Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the cover/thumbnail selection UX to support video frame extraction via ffmpeg, a timeline-based frame picker, in-dialog material library, and unified landscape/portrait editing.

**Architecture:** Backend ffmpeg service extracts 1fps thumbnails on video upload. Frontend shows recommended frames on the publish page, and a full-featured editor dialog with timeline scrubber, crop canvas, and inline material library sidebar.

**Tech Stack:** Python subprocess (ffmpeg/ffprobe), Vue 3 + Element Plus, HTML5 Canvas for cropping

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/services/__init__.py` | Package init (empty) |
| `backend/services/ffmpeg_service.py` | Locate ffmpeg binary, extract frames, get duration, get HD frame |
| `backend/routes/frames.py` | Flask Blueprint with 4 frame API endpoints |

### Backend — Modified Files
| File | Change |
|------|--------|
| `backend/app.py` | Register `frames` Blueprint |
| `backend/requirements.txt` | No new deps (subprocess only) |

### Frontend — New Files
| File | Responsibility |
|------|---------------|
| `frontend/src/api/frame.js` | API client for frame endpoints |
| `frontend/src/components/VideoTimeline.vue` | Timeline scrubber component |
| `frontend/src/components/CoverEditorDialog.vue` | Full cover editor modal |
| `frontend/src/components/CoverCard.vue` | Single cover card with recommended frames |

### Frontend — Modified Files
| File | Change |
|------|--------|
| `frontend/src/views/PublishCenter.vue` | Replace cover section with `CoverCard`, wire up `CoverEditorDialog` |
| `frontend/vite.config.js` | Add proxy rules for `/api/extract-frames`, `/api/frames-status`, `/api/frames`, `/api/frame-image` |

---

## Task 1: Backend ffmpeg service

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/ffmpeg_service.py`
- Test: manual via curl after Task 2

- [ ] **Step 1: Create services package**

Create `backend/services/__init__.py` (empty file).

- [ ] **Step 2: Create ffmpeg_service.py**

```python
# backend/services/ffmpeg_service.py
import os
import sys
import subprocess
import json
import shutil
import threading
from pathlib import Path
from loguru import logger

# Active extraction tasks: { video_path: { "status", "total_frames", "duration" } }
_extraction_tasks: dict[str, dict] = {}
_extraction_lock = threading.Lock()


def _find_ffmpeg() -> str:
    """Locate ffmpeg binary with priority: PyInstaller bundle > local bin/ > system PATH."""
    # 1. PyInstaller bundle
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            bundled = os.path.join(meipass, 'bin', 'ffmpeg')
            if os.path.isfile(bundled):
                return bundled

    # 2. Local bin/
    local_bin = Path(__file__).parent.parent / 'bin' / 'ffmpeg'
    if local_bin.is_file():
        return str(local_bin)

    # 3. System PATH
    found = shutil.which('ffmpeg')
    if found:
        return found

    raise FileNotFoundError(
        "ffmpeg not found. Place ffmpeg binary at backend/bin/ffmpeg or install system-wide."
    )


def _find_ffprobe() -> str:
    """Locate ffprobe binary using the same priority as ffmpeg."""
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', '')
        if meipass:
            bundled = os.path.join(meipass, 'bin', 'ffprobe')
            if os.path.isfile(bundled):
                return bundled

    local_bin = Path(__file__).parent.parent / 'bin' / 'ffprobe'
    if local_bin.is_file():
        return str(local_bin)

    found = shutil.which('ffprobe')
    if found:
        return found

    raise FileNotFoundError("ffprobe not found.")


FFMPEG = _find_ffmpeg()
FFPROBE = _find_ffprobe()


def get_video_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    cmd = [
        FFPROBE, '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def _frames_dir(base_dir: Path, video_path: str) -> Path:
    """Return the frames cache directory for a given video."""
    # Use the filename (with UUID prefix) as directory name
    video_name = Path(video_path).stem
    return base_dir / 'frames' / video_name


def _extract_frames_sync(base_dir: Path, video_path: str):
    """Extract 1fps thumbnails synchronously. Called in a background thread."""
    frames_out = _frames_dir(base_dir, video_path)
    frames_out.mkdir(parents=True, exist_ok=True)

    try:
        duration = get_video_duration(video_path)
    except Exception as e:
        logger.error(f"Failed to get video duration: {e}")
        with _extraction_lock:
            _extraction_tasks[video_path] = {"status": "error", "error": str(e)}
        return

    with _extraction_lock:
        _extraction_tasks[video_path] = {
            "status": "processing",
            "total_frames": 0,
            "duration": duration,
        }

    cmd = [
        FFMPEG, '-i', video_path,
        '-vf', 'fps=1,scale=320:-1',
        '-q:v', '3',
        '-y',
        str(frames_out / 'frame_%d.jpg')
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg extraction timed out")
        with _extraction_lock:
            _extraction_tasks[video_path]["status"] = "error"
        return

    # Count extracted frames
    frame_files = sorted(frames_out.glob('frame_*.jpg'))
    total = len(frame_files)

    with _extraction_lock:
        _extraction_tasks[video_path] = {
            "status": "done",
            "total_frames": total,
            "duration": duration,
        }

    logger.info(f"Extracted {total} frames from {video_path}")


def start_frame_extraction(base_dir: Path, video_path: str) -> str:
    """Start async frame extraction. Returns video_path as task identifier."""
    # Check if already done or in progress
    with _extraction_lock:
        task = _extraction_tasks.get(video_path)
        if task and task['status'] in ('done', 'processing'):
            return video_path

    thread = threading.Thread(
        target=_extract_frames_sync,
        args=(base_dir, video_path),
        daemon=True,
    )
    thread.start()
    return video_path


def get_extraction_status(video_path: str) -> dict:
    """Return extraction status for a video."""
    with _extraction_lock:
        return _extraction_tasks.get(video_path, {"status": "not_started"})


def get_frame_list(base_dir: Path, video_path: str) -> dict:
    """Return list of extracted frame thumbnails with URLs and durations."""
    frames_out = _frames_dir(base_dir, video_path)
    if not frames_out.exists():
        return {"frames": [], "duration": 0}

    frame_files = sorted(frames_out.glob('frame_*.jpg'))
    frames = []
    for f in frame_files:
        # frame_1.jpg = second 0, frame_2.jpg = second 1, etc.
        seconds = int(f.stem.split('_')[1]) - 1
        frames.append({
            "url": f"/api/frame-image?video_path={video_path}&seconds={seconds}&thumbnail=1",
            "seconds": seconds,
        })

    duration = 0.0
    with _extraction_lock:
        task = _extraction_tasks.get(video_path)
        if task:
            duration = task.get('duration', 0)

    return {"frames": frames, "duration": duration}


def get_frame_image_path(base_dir: Path, video_path: str, seconds: int, thumbnail: bool = False) -> str | None:
    """Return file path for a specific frame. Extracts on-demand if not cached."""
    if thumbnail:
        # Return pre-extracted 320px thumbnail
        frames_out = _frames_dir(base_dir, video_path)
        thumb = frames_out / f'frame_{seconds + 1}.jpg'
        if thumb.exists():
            return str(thumb)
        return None

    # HD frame: check cache first, then extract
    frames_out = _frames_dir(base_dir, video_path)
    hd_cache = frames_out / f'hd_{seconds}.jpg'
    if hd_cache.exists():
        return str(hd_cache)

    # Extract HD frame on demand
    frames_out.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, '-i', video_path,
        '-vf', f'select=eq(n\\,{seconds})',
        '-vframes', '1',
        '-q:v', '2',
        '-y',
        str(hd_cache)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or not hd_cache.exists():
        logger.error(f"Failed to extract HD frame at {seconds}s: {result.stderr}")
        return None

    return str(hd_cache)
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/
git commit -m "feat: add ffmpeg service for video frame extraction"
```

---

## Task 2: Backend frame API routes

**Files:**
- Create: `backend/routes/__init__.py` (empty)
- Create: `backend/routes/frames.py`
- Modify: `backend/app.py` — register Blueprint + add proxy config
- Modify: `frontend/vite.config.js` — add proxy rules

- [ ] **Step 1: Create routes package**

Create `backend/routes/__init__.py` (empty file).

- [ ] **Step 2: Create frames Blueprint**

```python
# backend/routes/frames.py
import os
from flask import Blueprint, request, jsonify, send_file
from conf import BASE_DIR
from services.ffmpeg_service import (
    start_frame_extraction,
    get_extraction_status,
    get_frame_list,
    get_frame_image_path,
)

frames_bp = Blueprint('frames', __name__)


@frames_bp.post('/api/extract-frames')
def extract_frames():
    data = request.get_json(force=True)
    video_path = data.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    # Resolve actual file path on disk
    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        # Maybe video_path is already absolute
        full_path = video_path
    if not os.path.isfile(full_path):
        return jsonify({"code": 404, "msg": "Video file not found"}), 404

    task_id = start_frame_extraction(BASE_DIR, full_path)
    return jsonify({"code": 200, "data": {"task_id": task_id}})


@frames_bp.get('/api/frames-status')
def frames_status():
    video_path = request.args.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        full_path = video_path

    status = get_extraction_status(full_path)
    return jsonify({"code": 200, "data": status})


@frames_bp.get('/api/frames')
def get_frames():
    video_path = request.args.get('video_path', '')
    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        full_path = video_path

    result = get_frame_list(BASE_DIR, full_path)
    return jsonify({"code": 200, "data": result})


@frames_bp.get('/api/frame-image')
def get_frame_image():
    video_path = request.args.get('video_path', '')
    seconds = request.args.get('seconds', '0')
    thumbnail = request.args.get('thumbnail', '0') == '1'

    if not video_path:
        return jsonify({"code": 400, "msg": "video_path is required"}), 400

    try:
        seconds = int(seconds)
    except ValueError:
        return jsonify({"code": 400, "msg": "seconds must be integer"}), 400

    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if not os.path.isfile(full_path):
        full_path = video_path

    image_path = get_frame_image_path(BASE_DIR, full_path, seconds, thumbnail=thumbnail)
    if not image_path or not os.path.isfile(image_path):
        return jsonify({"code": 404, "msg": "Frame not found"}), 404

    return send_file(image_path, mimetype='image/jpeg')
```

- [ ] **Step 3: Register Blueprint in app.py**

At the top of `backend/app.py`, add import:
```python
from routes.frames import frames_bp
```

After the existing Blueprint registration (around line 49-52), add:
```python
app.register_blueprint(frames_bp)
```

- [ ] **Step 4: Add Vite proxy rules**

In `frontend/vite.config.js`, add these proxy entries inside `server.proxy`:
```javascript
'/api/extract-frames': {
  target: 'http://localhost:5409',
  changeOrigin: true,
},
'/api/frames-status': {
  target: 'http://localhost:5409',
  changeOrigin: true,
},
'/api/frames': {
  target: 'http://localhost:5409',
  changeOrigin: true,
},
'/api/frame-image': {
  target: 'http://localhost:5409',
  changeOrigin: true,
},
```

- [ ] **Step 5: Manual test**

1. Place an ffmpeg binary at `backend/bin/ffmpeg` (or ensure system ffmpeg available)
2. Start backend: `cd backend && python app.py`
3. Upload a video via the existing UI
4. Test extraction:
```bash
curl -X POST http://localhost:5409/api/extract-frames \
  -H 'Content-Type: application/json' \
  -d '{"video_path": "<uploaded_filename>"}'
```
5. Check status: `curl http://localhost:5409/api/frames-status?video_path=<path>`
6. List frames: `curl http://localhost:5409/api/frames?video_path=<path>`

- [ ] **Step 6: Commit**

```bash
git add backend/routes/ backend/app.py frontend/vite.config.js
git commit -m "feat: add frame extraction API endpoints and vite proxy"
```

---

## Task 3: Frontend frame API client

**Files:**
- Create: `frontend/src/api/frame.js`

- [ ] **Step 1: Create frame API module**

```javascript
// frontend/src/api/frame.js
import http from '@/utils/request'

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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/frame.js
git commit -m "feat: add frontend frame API client"
```

---

## Task 4: VideoTimeline component

**Files:**
- Create: `frontend/src/components/VideoTimeline.vue`

- [ ] **Step 1: Create VideoTimeline component**

```vue
<!-- frontend/src/components/VideoTimeline.vue -->
<template>
  <div class="video-timeline">
    <div class="timeline-track" ref="trackRef" @mousedown="onTrackMouseDown">
      <div class="timeline-thumbs">
        <img
          v-for="frame in frames"
          :key="frame.seconds"
          :src="frame.url"
          class="timeline-thumb"
          :style="{ width: thumbWidth + 'px' }"
          draggable="false"
        />
      </div>
      <div
        class="timeline-slider"
        :style="{ left: sliderLeft + 'px', width: thumbWidth + 'px' }"
      ></div>
    </div>
    <div class="timeline-markers">
      <span v-for="marker in timeMarkers" :key="marker.seconds" class="time-marker" :style="{ left: marker.position + 'px' }">
        {{ marker.label }}
      </span>
    </div>
    <div class="timeline-time-display">
      {{ formatTime(modelValue) }} / {{ formatTime(duration) }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const THUMB_WIDTH = 80
const MARKER_INTERVAL = 10 // show time marker every 10 seconds

const props = defineProps({
  /** Array of { url: string, seconds: number } */
  frames: { type: Array, default: () => [] },
  /** Video duration in seconds */
  duration: { type: Number, default: 0 },
  /** Currently selected second */
  modelValue: { type: Number, default: 0 },
})

const emit = defineEmits(['update:modelValue'])

const trackRef = ref(null)
const thumbWidth = THUMB_WIDTH
const trackWidth = computed(() => props.frames.length * THUMB_WIDTH)

const sliderLeft = computed(() => props.modelValue * THUMB_WIDTH)

const timeMarkers = computed(() => {
  const markers = []
  for (let s = 0; s <= props.duration; s += MARKER_INTERVAL) {
    markers.push({
      seconds: s,
      label: formatTime(s),
      position: s * THUMB_WIDTH,
    })
  }
  return markers
})

function formatTime(secs) {
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function onTrackMouseDown(e) {
  e.preventDefault()
  const track = trackRef.value
  if (!track) return

  const updatePosition = (clientX) => {
    const rect = track.getBoundingClientRect()
    const scrollLeft = track.scrollLeft || 0
    const x = clientX - rect.left + scrollLeft
    const seconds = Math.round(x / THUMB_WIDTH)
    const clamped = Math.max(0, Math.min(seconds, props.frames.length - 1))
    emit('update:modelValue', clamped)
  }

  updatePosition(e.clientX)

  const onMove = (ev) => updatePosition(ev.clientX)
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
</script>

<style scoped lang="scss">
.video-timeline {
  user-select: none;
}
.timeline-track {
  overflow-x: auto;
  overflow-y: hidden;
  position: relative;
  height: 56px;
  background: #1a1a1a;
  border-radius: 4px;
  cursor: pointer;
  scrollbar-width: thin;
  scrollbar-color: #555 #222;

  &::-webkit-scrollbar { height: 4px; }
  &::-webkit-scrollbar-thumb { background: #555; border-radius: 2px; }
  &::-webkit-scrollbar-track { background: #222; }
}
.timeline-thumbs {
  display: flex;
  height: 100%;
}
.timeline-thumb {
  height: 100%;
  object-fit: cover;
  flex-shrink: 0;
  pointer-events: none;
  opacity: 0.7;
}
.timeline-slider {
  position: absolute;
  top: 0;
  height: 100%;
  border: 2px solid var(--el-color-primary);
  background: rgba(64, 158, 255, 0.15);
  pointer-events: none;
  transition: left 0.05s ease;
}
.timeline-markers {
  position: relative;
  height: 18px;
  margin-top: 2px;
}
.time-marker {
  position: absolute;
  top: 0;
  font-size: 10px;
  color: #999;
  transform: translateX(-50%);
}
.timeline-time-display {
  margin-top: 4px;
  font-size: 12px;
  color: #ccc;
  text-align: center;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/VideoTimeline.vue
git commit -m "feat: add VideoTimeline component with thumbnail scrubber"
```

---

## Task 5: CoverEditorDialog component

**Files:**
- Create: `frontend/src/components/CoverEditorDialog.vue`

This is the largest task. The dialog contains: Tab switcher (landscape/portrait), preview/crop canvas, timeline, upload button, inline material library sidebar.

- [ ] **Step 1: Create CoverEditorDialog component**

```vue
<!-- frontend/src/components/CoverEditorDialog.vue -->
<template>
  <el-dialog
    v-model="visible"
    title="编辑封面"
    width="900px"
    class="cover-editor-dialog"
    :close-on-click-modal="false"
    @closed="onClosed"
  >
    <!-- Tab switcher -->
    <div class="cover-editor-tabs">
      <button
        :class="['tab-btn', { active: activeTab === 'landscape' }]"
        @click="switchTab('landscape')"
      >横版 16:9</button>
      <button
        :class="['tab-btn', { active: activeTab === 'portrait' }]"
        @click="switchTab('portrait')"
      >竖版 9:16</button>
    </div>

    <div class="cover-editor-body">
      <!-- Left: preview + timeline -->
      <div class="editor-main">
        <!-- Crop area -->
        <div class="crop-area">
          <div v-if="!currentImageSrc" class="crop-empty">
            <span>选择时间轴帧、上传图片或从右侧素材库选取</span>
          </div>
          <div v-else class="crop-canvas-wrap" ref="canvasWrapRef">
            <canvas ref="cropCanvasRef" class="crop-canvas"></canvas>
            <div
              class="crop-selection"
              :style="cropSelectionStyle"
              @mousedown="startCropDrag"
            >
              <div class="crop-handle top-left" data-handle="tl"></div>
              <div class="crop-handle top-right" data-handle="tr"></div>
              <div class="crop-handle bottom-left" data-handle="bl"></div>
              <div class="crop-handle bottom-right" data-handle="br"></div>
            </div>
          </div>
          <div v-if="currentImageSrc" class="crop-info">
            <span>{{ activeTab === 'portrait' ? '9:16' : '16:9' }}</span>
          </div>
        </div>

        <!-- Timeline -->
        <div class="timeline-section" v-if="frames.length > 0">
          <VideoTimeline
            :frames="frames"
            :duration="videoDuration"
            v-model="selectedSecond"
            @update:modelValue="onTimelineSelect"
          />
        </div>

        <!-- Upload button -->
        <div class="editor-upload">
          <el-button size="small" @click="triggerLocalUpload">
            <el-icon><Upload /></el-icon> 上传图片
          </el-button>
          <input
            ref="fileInputRef"
            type="file"
            accept="image/*"
            style="display: none"
            @change="onLocalFileSelected"
          />
        </div>
      </div>

      <!-- Right: material library sidebar -->
      <div class="editor-sidebar">
        <div class="sidebar-title">素材库</div>
        <div class="sidebar-grid" v-if="imageMaterials.length > 0">
          <div
            v-for="mat in imageMaterials"
            :key="mat.id"
            class="sidebar-thumb"
            @click="onMaterialClick(mat)"
          >
            <img :src="getMaterialUrl(mat)" :alt="mat.filename" />
          </div>
        </div>
        <div v-else class="sidebar-empty">暂无图片素材</div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer-right">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="confirmCrop">确认</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import http from '@/utils/request'
import { materialApi } from '@/api/material'
import { frameApi } from '@/api/frame'
import VideoTimeline from './VideoTimeline.vue'

const props = defineProps({
  /** Landscape video data { path, url, name, ... } */
  videoLandscape: { type: Object, default: null },
  /** Portrait video data */
  videoPortrait: { type: Object, default: null },
  /** Existing landscape cover data */
  coverLandscape: { type: Object, default: null },
  /** Existing portrait cover data */
  coverPortrait: { type: Object, default: null },
  /** Materials list from store */
  materials: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:coverLandscape', 'update:coverPortrait'])

const visible = ref(false)
const activeTab = ref('landscape')
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || ''

// Frame data
const frames = ref([])
const videoDuration = ref(0)
const selectedSecond = ref(0)

// Crop state
const cropCanvasRef = ref(null)
const canvasWrapRef = ref(null)
const fileInputRef = ref(null)
const cropImage = ref(null)
const currentImageSrc = ref('')
const cropDisplayScale = ref(1)
const cropRect = reactive({ x: 0, y: 0, w: 0, h: 0 })
const cropDragState = ref(null)

// Per-tab state
const tabState = reactive({
  landscape: { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } },
  portrait: { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } },
})

// Materials
const imageMaterials = computed(() => {
  const imgExts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
  return props.materials.filter(m =>
    imgExts.some(ext => m.filename.toLowerCase().endsWith(ext))
  )
})

const aspectRatio = computed(() => activeTab.value === 'portrait' ? 9 / 16 : 16 / 9)

const cropSelectionStyle = computed(() => ({
  left: cropRect.x * cropDisplayScale.value + 'px',
  top: cropRect.y * cropDisplayScale.value + 'px',
  width: cropRect.w * cropDisplayScale.value + 'px',
  height: cropRect.h * cropDisplayScale.value + 'px',
}))

function getMaterialUrl(mat) {
  return materialApi.getMaterialPreviewUrl(mat.file_path.split('/').pop())
}

/** Open the dialog */
function open(tab = 'landscape') {
  activeTab.value = tab
  visible.value = true
  loadFrames()
  loadTabState()
}

/** Resolve which video to use for the current tab */
function currentVideoPath() {
  if (activeTab.value === 'landscape') {
    return props.videoLandscape?.path || props.videoPortrait?.path || ''
  }
  return props.videoPortrait?.path || props.videoLandscape?.path || ''
}

async function loadFrames() {
  const videoPath = currentVideoPath()
  if (!videoPath) return

  // Trigger extraction (idempotent)
  try {
    await frameApi.extractFrames(videoPath)
  } catch { /* may already be extracting */ }

  // Poll until done
  const poll = async (retries = 30) => {
    for (let i = 0; i < retries; i++) {
      try {
        const resp = await frameApi.getFramesStatus(videoPath)
        if (resp.data?.status === 'done') break
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 1000))
    }
  }
  await poll()

  // Load frame list
  try {
    const resp = await frameApi.getFrames(videoPath)
    if (resp.data) {
      frames.value = resp.data.frames || []
      videoDuration.value = resp.data.duration || 0
    }
  } catch { /* ignore */ }
}

function loadTabState() {
  const state = tabState[activeTab.value]
  if (state.imageSrc) {
    currentImageSrc.value = state.imageSrc
    loadImageToCanvas(state.imageSrc)
  } else {
    // Check if existing cover
    const cover = activeTab.value === 'landscape' ? props.coverLandscape : props.coverPortrait
    if (cover?.url) {
      currentImageSrc.value = cover.url
      loadImageToCanvas(cover.url)
    } else {
      currentImageSrc.value = ''
      cropImage.value = null
    }
  }
}

function saveTabState() {
  const state = tabState[activeTab.value]
  state.imageSrc = currentImageSrc.value
  state.cropRect = { ...cropRect }
}

function switchTab(tab) {
  saveTabState()
  activeTab.value = tab
  loadTabState()
}

function loadImageToCanvas(src) {
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    cropImage.value = img
    nextTick(() => initCropCanvas(img))
  }
  img.src = src
}

function initCropCanvas(img) {
  const canvas = cropCanvasRef.value
  if (!canvas) return

  const maxW = 520
  const maxH = 380
  const scale = Math.min(maxW / img.width, maxH / img.height, 1)
  cropDisplayScale.value = scale

  canvas.width = img.width * scale
  canvas.height = img.height * scale

  const ctx = canvas.getContext('2d')
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

  // Restore saved crop rect if exists
  const saved = tabState[activeTab.value].cropRect
  if (saved.w > 0 && saved.h > 0) {
    Object.assign(cropRect, saved)
    return
  }

  // Init crop rect: centered with target aspect ratio
  const ratio = aspectRatio.value
  let rw = img.width * 0.8
  let rh = rw / ratio
  if (rh > img.height * 0.8) {
    rh = img.height * 0.8
    rw = rh * ratio
  }
  cropRect.x = (img.width - rw) / 2
  cropRect.y = (img.height - rh) / 2
  cropRect.w = rw
  cropRect.h = rh
}

// -- Timeline interaction --
function onTimelineSelect(seconds) {
  const videoPath = currentVideoPath()
  const url = frameApi.getFrameImageUrl(videoPath, seconds, false)
  currentImageSrc.value = url
  loadImageToCanvas(url)
}

// -- Material interaction --
function onMaterialClick(mat) {
  const url = getMaterialUrl(mat)
  currentImageSrc.value = url
  loadImageToCanvas(url)
}

// -- Local upload --
function triggerLocalUpload() {
  fileInputRef.value?.click()
}

function onLocalFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const url = URL.createObjectURL(file)
  currentImageSrc.value = url
  loadImageToCanvas(url)
  e.target.value = ''
}

// -- Crop drag (same logic as existing PublishCenter) --
function startCropDrag(e) {
  e.preventDefault()
  const handle = e.target.dataset.handle
  cropDragState.value = {
    type: handle || 'move',
    startX: e.clientX,
    startY: e.clientY,
    origRect: { ...cropRect },
  }

  const onMove = (ev) => {
    if (!cropDragState.value) return
    const dx = (ev.clientX - cropDragState.value.startX) / cropDisplayScale.value
    const dy = (ev.clientY - cropDragState.value.startY) / cropDisplayScale.value
    const orig = cropDragState.value.origRect
    const img = cropImage.value
    if (!img) return
    const ratio = aspectRatio.value
    const type = cropDragState.value.type

    if (type === 'move') {
      cropRect.x = Math.max(0, Math.min(img.width - orig.w, orig.x + dx))
      cropRect.y = Math.max(0, Math.min(img.height - orig.h, orig.y + dy))
    } else {
      let newW = orig.w
      let newH = orig.h
      if (type === 'br') { newW = orig.w + dx; newH = newW / ratio }
      else if (type === 'bl') { newW = orig.w - dx; newH = newW / ratio }
      else if (type === 'tr') { newW = orig.w + dx; newH = newW / ratio }
      else if (type === 'tl') { newW = orig.w - dx; newH = newW / ratio }

      newW = Math.max(60, newW)
      newH = newW / ratio

      if (type === 'tl' || type === 'bl') cropRect.x = orig.x + orig.w - newW
      if (type === 'tl' || type === 'tr') cropRect.y = orig.y + orig.h - newH

      cropRect.x = Math.max(0, cropRect.x)
      cropRect.y = Math.max(0, cropRect.y)
      if (cropRect.x + newW > img.width) newW = img.width - cropRect.x
      if (cropRect.y + newH > img.height) newH = img.height - cropRect.y
      newH = newW / ratio

      cropRect.w = newW
      cropRect.h = newH
    }
  }

  const onUp = () => {
    cropDragState.value = null
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// -- Confirm crop --
async function confirmCrop() {
  saveTabState()
  const img = cropImage.value
  if (!img) {
    ElMessage.warning('请先选择一张图片')
    return
  }

  // Export at target resolution: landscape 1920x1080, portrait 1080x1920
  const targetW = activeTab.value === 'portrait' ? 1080 : 1920
  const targetH = activeTab.value === 'portrait' ? 1920 : 1080

  const offscreen = document.createElement('canvas')
  offscreen.width = targetW
  offscreen.height = targetH
  const ctx = offscreen.getContext('2d')
  ctx.drawImage(img, cropRect.x, cropRect.y, cropRect.w, cropRect.h, 0, 0, targetW, targetH)

  const blob = await new Promise(resolve => offscreen.toBlob(resolve, 'image/jpeg', 0.92))
  if (!blob) {
    ElMessage.error('裁剪导出失败')
    return
  }

  const formData = new FormData()
  formData.append('file', blob, `cover_${activeTab.value}_${Date.now()}.jpg`)

  try {
    const resp = await http.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (resp.code === 200) {
      const filePath = resp.data.filepath || resp.data
      const filename = filePath.split('/').pop()
      const coverData = {
        name: `cover_${activeTab.value}.jpg`,
        url: materialApi.getMaterialPreviewUrl(filename),
        path: filePath,
        size: blob.size,
        type: 'image/jpeg',
      }
      if (activeTab.value === 'portrait') {
        emit('update:coverPortrait', coverData)
      } else {
        emit('update:coverLandscape', coverData)
      }
      ElMessage.success('封面设置成功')
      visible.value = false
    } else {
      ElMessage.error(resp.msg || '上传失败')
    }
  } catch {
    ElMessage.error('封面上传失败')
  }
}

function onClosed() {
  frames.value = []
  videoDuration.value = 0
  currentImageSrc.value = ''
  cropImage.value = null
  tabState.landscape = { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } }
  tabState.portrait = { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } }
}

defineExpose({ open })
</script>

<style scoped lang="scss">
.cover-editor-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.tab-btn {
  padding: 6px 16px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  &.active {
    background: var(--el-color-primary);
    color: #fff;
    border-color: var(--el-color-primary);
  }
}
.cover-editor-body {
  display: flex;
  gap: 16px;
}
.editor-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.crop-area {
  background: #111;
  border-radius: 4px;
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.crop-empty {
  color: #999;
  font-size: 13px;
}
.crop-canvas-wrap {
  position: relative;
  display: inline-block;
}
.crop-canvas {
  display: block;
  max-width: 100%;
}
.crop-selection {
  position: absolute;
  border: 2px solid var(--el-color-primary);
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);
  cursor: move;
}
.crop-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  background: #fff;
  border: 1px solid var(--el-color-primary);
  border-radius: 50%;
  &.top-left { top: -5px; left: -5px; cursor: nw-resize; }
  &.top-right { top: -5px; right: -5px; cursor: ne-resize; }
  &.bottom-left { bottom: -5px; left: -5px; cursor: sw-resize; }
  &.bottom-right { bottom: -5px; right: -5px; cursor: se-resize; }
}
.crop-info {
  text-align: center;
  color: #999;
  font-size: 12px;
  margin-top: 4px;
}
.editor-upload {
  display: flex;
  gap: 8px;
}
.editor-sidebar {
  width: 180px;
  border-left: 1px solid #eee;
  padding-left: 12px;
  overflow-y: auto;
  max-height: 420px;
}
.sidebar-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
  color: #666;
}
.sidebar-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.sidebar-thumb {
  aspect-ratio: 1;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  &:hover { border-color: var(--el-color-primary); }
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
}
.sidebar-empty {
  color: #999;
  font-size: 12px;
  text-align: center;
  padding: 20px 0;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/CoverEditorDialog.vue
git commit -m "feat: add CoverEditorDialog with timeline, crop, and material sidebar"
```

---

## Task 6: CoverCard component

**Files:**
- Create: `frontend/src/components/CoverCard.vue`

This component replaces the inline cover card in PublishCenter.vue. It shows recommended frames, current cover preview, and action buttons.

- [ ] **Step 1: Create CoverCard component**

```vue
<!-- frontend/src/components/CoverCard.vue -->
<template>
  <div class="cover-card">
    <div class="cover-card-label">
      <span>{{ label }}</span>
      <span class="cover-ratio">{{ ratioLabel }}</span>
    </div>

    <!-- Recommended frames row (shown when video exists) -->
    <div v-if="recommendedFrames.length > 0" class="recommended-frames">
      <div
        v-for="frame in recommendedFrames"
        :key="frame.seconds"
        :class="['frame-thumb', { active: isSelected(frame.seconds) }]"
        @click="onFrameClick(frame)"
      >
        <img :src="frame.url" />
        <div v-if="isSelected(frame.seconds)" class="frame-check">
          <el-icon :size="12"><Check /></el-icon>
        </div>
      </div>
      <button class="frame-thumb edit-btn" @click="$emit('edit')">
        <el-icon :size="20"><Edit /></el-icon>
        <span>编辑</span>
      </button>
    </div>

    <!-- Cover preview or empty -->
    <div v-if="modelValue" class="cover-preview-wrap">
      <img :src="modelValue.url" class="cover-preview" />
      <div class="cover-preview-overlay">
        <button class="overlay-btn" @click="$emit('edit')">编辑</button>
        <button class="overlay-btn" @click="triggerUpload">更换</button>
        <button class="overlay-btn danger" @click="$emit('update:modelValue', null)">删除</button>
      </div>
    </div>
    <div v-else-if="recommendedFrames.length === 0" class="cover-empty" @click="triggerUpload">
      <el-icon :size="28"><Picture /></el-icon>
      <span class="cover-empty-text">上传{{ label }}</span>
    </div>

    <!-- Action buttons -->
    <div class="cover-card-actions">
      <button class="cover-action-btn" @click="triggerUpload">
        <el-icon :size="14"><Upload /></el-icon><span>上传</span>
      </button>
      <button class="cover-action-btn" @click="$emit('open-library')">
        <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
      </button>
    </div>

    <!-- Hidden file input for quick upload -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      style="display: none"
      @change="onFileSelected"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture, Upload, Edit, Check } from '@element-plus/icons-vue'
import http from '@/utils/request'
import { materialApi } from '@/api/material'

const props = defineProps({
  label: { type: String, default: '横版封面' },
  ratioLabel: { type: String, default: '16:9' },
  modelValue: { type: Object, default: null },
  recommendedFrames: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'edit', 'open-library'])
const fileInputRef = ref(null)

function isSelected(seconds) {
  return props.modelValue?._fromFrame === seconds
}

async function onFrameClick(frame) {
  // Frame URL points to thumbnail; we need to set it as cover directly
  // For now, use the thumbnail as the cover (user can refine in editor)
  const coverData = {
    name: `frame_${frame.seconds}s.jpg`,
    url: frame.url,
    path: '',
    size: 0,
    type: 'image/jpeg',
    _fromFrame: frame.seconds,
  }
  emit('update:modelValue', coverData)
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return

  const formData = new FormData()
  formData.append('file', file)

  try {
    const resp = await http.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (resp.code === 200) {
      const filePath = resp.data.filepath || resp.data
      const filename = filePath.split('/').pop()
      emit('update:modelValue', {
        name: file.name,
        url: materialApi.getMaterialPreviewUrl(filename),
        path: filePath,
        size: file.size,
        type: file.type,
      })
      ElMessage.success('封面上传成功')
    } else {
      ElMessage.error(resp.msg || '上传失败')
    }
  } catch {
    ElMessage.error('上传失败')
  }
  e.target.value = ''
}
</script>

<style scoped lang="scss">
.cover-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
  background: #fafafa;
}
.cover-card-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 500;
}
.cover-ratio {
  font-size: 11px;
  color: #999;
  background: #f0f0f0;
  padding: 1px 6px;
  border-radius: 3px;
}
.recommended-frames {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
  overflow-x: auto;
}
.frame-thumb {
  width: 52px;
  height: 36px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  flex-shrink: 0;
  position: relative;
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  &.active {
    border-color: var(--el-color-primary);
  }
  &:hover { border-color: var(--el-color-primary-light-3); }
}
.frame-check {
  position: absolute;
  top: 2px;
  right: 2px;
  background: var(--el-color-primary);
  color: #fff;
  border-radius: 50%;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.edit-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #fff;
  border: 2px dashed #dcdfe6;
  font-size: 10px;
  color: #999;
  gap: 2px;
  &:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); }
}
.cover-preview-wrap {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 8px;
}
.cover-preview {
  width: 100%;
  display: block;
}
.cover-preview-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}
.cover-preview-wrap:hover .cover-preview-overlay {
  opacity: 1;
}
.overlay-btn {
  padding: 4px 12px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  &:hover { background: rgba(255, 255, 255, 0.4); }
  &.danger:hover { background: rgba(245, 108, 108, 0.7); }
}
.cover-empty {
  border: 2px dashed #dcdfe6;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  cursor: pointer;
  color: #c0c4cc;
  margin-bottom: 8px;
  &:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); }
}
.cover-empty-text {
  font-size: 13px;
  margin-top: 6px;
}
.cover-card-actions {
  display: flex;
  gap: 8px;
}
.cover-action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  &:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); }
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/CoverCard.vue
git commit -m "feat: add CoverCard component with recommended frames and quick actions"
```

---

## Task 7: Integrate into PublishCenter.vue

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

This task replaces the old inline cover section (template lines 154-213) with the new `CoverCard` components, wires up the `CoverEditorDialog`, adds frame extraction triggers on video upload, and removes the old cover upload/crop/material-library dialogs.

- [ ] **Step 1: Add imports**

At the top of the `<script setup>` section, add:
```javascript
import CoverCard from '@/components/CoverCard.vue'
import CoverEditorDialog from '@/components/CoverEditorDialog.vue'
import { frameApi } from '@/api/frame'
```

- [ ] **Step 2: Add ref for CoverEditorDialog and frame data**

Add new reactive state:
```javascript
const coverEditorRef = ref(null)
const landscapeFrames = ref([])
const portraitFrames = ref([])
const landscapeDuration = ref(0)
const portraitDuration = ref(0)
```

- [ ] **Step 3: Add frame extraction trigger on video upload**

After `handleVideoUploadSuccess` sets `commonConfig.videoLandscape` or `commonConfig.videoPortrait`, add frame extraction:
```javascript
async function triggerFrameExtraction(videoData, type) {
  if (!videoData?.path) return
  try {
    await frameApi.extractFrames(videoData.path)
    // Poll and load recommended frames
    const poll = async (retries = 30) => {
      for (let i = 0; i < retries; i++) {
        const resp = await frameApi.getFramesStatus(videoData.path)
        if (resp.data?.status === 'done') break
        await new Promise(r => setTimeout(r, 1000))
      }
    }
    await poll()
    const resp = await frameApi.getFrames(videoData.path)
    if (resp.data) {
      const allFrames = resp.data.frames || []
      const dur = resp.data.duration || 0
      // Pick 6 recommended frames evenly
      const recommended = pickRecommendedFrames(allFrames, 6)
      if (type === 'landscape') {
        landscapeFrames.value = recommended
        landscapeDuration.value = dur
      } else {
        portraitFrames.value = recommended
        portraitDuration.value = dur
      }
    }
  } catch (e) {
    console.error('Frame extraction failed:', e)
  }
}

function pickRecommendedFrames(frames, count) {
  if (frames.length <= count) return frames
  const result = []
  // Always include first frame
  result.push(frames[0])
  // Pick evenly from remaining
  for (let i = 1; i < count - 1; i++) {
    const idx = Math.round((frames.length - 1) * i / (count - 1))
    result.push(frames[idx])
  }
  // Always include last frame
  result.push(frames[frames.length - 1])
  return result
}
```

In `handleVideoUploadSuccess`, after setting the video data and `ElMessage.success`, add:
```javascript
triggerFrameExtraction(videoData, videoUploadTarget.value)
```

- [ ] **Step 4: Replace cover section template**

Replace the entire `<!-- Cover Section -->` block (lines 154-213) with:
```html
<!-- Cover Section -->
<div class="media-section cover-section">
  <div class="section-label">封面</div>
  <div class="cover-grid">
    <CoverCard
      label="横版封面"
      ratio-label="16:9"
      v-model="commonConfig.coverLandscape"
      :recommended-frames="landscapeFrames"
      @edit="openCoverEditor('landscape')"
      @open-library="selectFromLibrary('cover', 'landscape')"
    />
    <CoverCard
      label="竖版封面"
      ratio-label="9:16"
      v-model="commonConfig.coverPortrait"
      :recommended-frames="portraitFrames"
      @edit="openCoverEditor('portrait')"
      @open-library="selectFromLibrary('cover', 'portrait')"
    />
  </div>
</div>

<CoverEditorDialog
  ref="coverEditorRef"
  :video-landscape="commonConfig.videoLandscape"
  :video-portrait="commonConfig.videoPortrait"
  :cover-landscape="commonConfig.coverLandscape"
  :cover-portrait="commonConfig.coverPortrait"
  :materials="materials"
  @update:cover-landscape="commonConfig.coverLandscape = $event"
  @update:cover-portrait="commonConfig.coverPortrait = $event"
/>
```

- [ ] **Step 5: Add openCoverEditor function**

```javascript
function openCoverEditor(tab = 'landscape') {
  coverEditorRef.value?.open(tab)
}
```

- [ ] **Step 6: Remove old cover dialogs**

Remove from template:
- Cover Upload Dialog (lines 586-619)
- Cover Crop Dialog (lines 621-654)

The old Material Library Dialog (lines 656-692) stays — it's still used for video material selection and as a fallback for the cover "素材库" quick button.

- [ ] **Step 7: Remove old cover-related functions that are now handled by components**

Remove from script:
- `triggerUploadCover` (replaced by CoverCard internal upload)
- `openCropDialog` (replaced by CoverEditorDialog)
- `initCropCanvas` (replaced by CoverEditorDialog)
- `startCropDrag` (replaced by CoverEditorDialog)
- `redrawCropCanvas` (replaced by CoverEditorDialog)
- `applyCrop` (replaced by CoverEditorDialog)
- `handleCoverUploadSuccess` (replaced by CoverCard internal upload)
- `handleCoverFileChange` (dead code)

Remove related refs:
- `coverUploadTarget`, `coverUploadDialogVisible`
- `cropDialogVisible`, `cropTarget`, `cropCanvasRef`, `cropImage`, `cropRect`, `cropDisplayScale`, `cropDragState`

- [ ] **Step 8: Update portrait ratio text**

In the remaining Material Library Dialog template, change `3:4` to `9:16` if it appears in any cover-related context.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: integrate CoverCard and CoverEditorDialog into PublishCenter"
```

---

## Task 8: Manual end-to-end test

- [ ] **Step 1: Start backend**

```bash
cd backend && python app.py
```

- [ ] **Step 2: Start frontend**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Test flow**

1. Open `http://localhost:5173/publish-center`
2. Upload a video (landscape or portrait)
3. Verify: after upload, recommended frames appear in cover cards
4. Click a recommended frame → it becomes the cover
5. Click "编辑" → CoverEditorDialog opens
6. Verify timeline shows frames
7. Drag timeline slider → preview updates
8. Verify material library sidebar shows image materials
9. Click a material → loads into preview
10. Click "上传图片" → select local file → loads into preview
11. Drag crop handles → crop area updates with correct aspect ratio
12. Switch tab to 竖版 9:16 → crop ratio changes
13. Click 确认 → cover is cropped and saved
14. Verify cover appears on PublishCenter cover card
15. Repeat for portrait cover

- [ ] **Step 4: Commit any fixes**

---

## Task 9: Update portrait crop ratio across platform backends

**Files:**
- Modify: `backend/impl/bilibili/platform.py` — check if 4:3 ratio sync affects cover upload
- Modify: any platform code that references 3:4 portrait ratio

- [ ] **Step 1: Search for 3:4 or 3/4 ratio references**

```bash
grep -rn "3.*/.*4\|3:4" backend/impl/ frontend/src/
```

Review each hit. Update portrait cover ratio from 3:4 to 9:16 where applicable in frontend code. Backend platform implementations use platform-specific ratios (e.g., Bilibili uses 4:3, Kuaishou uses 4:3) — these should NOT be changed as they match what the platforms expect.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "fix: update portrait cover ratio from 3:4 to 9:16 in frontend"
```

---

## Self-Review

**1. Spec coverage:**
- Section 1 (ffmpeg built-in + packaging): Task 1 ✓
- Section 2 (backend frame API): Task 1, 2 ✓
- Section 3 (publish page cover cards): Task 6, 7 ✓
- Section 4 (cover editor dialog): Task 4, 5 ✓
- Section 5 (data flow): wired through Tasks 3, 5, 6, 7 ✓
- Section 6 (ratio change 3:4 → 9:16): Task 9 ✓
- Section 7 (storage/performance): handled by ffmpeg_service cache dir ✓
- Section 8 (impact scope): all files listed ✓

**2. Placeholder scan:** No TBDs, TODOs, or vague steps found.

**3. Type consistency:**
- `coverData` shape `{ name, url, path, size, type }` consistent across CoverCard, CoverEditorDialog, and PublishCenter ✓
- Frame shape `{ url, seconds }` consistent between API and components ✓
- `activeTab` values `'landscape'|'portrait'` consistent throughout ✓
