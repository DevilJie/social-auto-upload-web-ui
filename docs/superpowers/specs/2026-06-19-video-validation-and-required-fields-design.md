# 视频素材增强与发布校验 — 设计文档

**日期：** 2026-06-19
**作者：** Claude
**状态：** 待用户审阅

---

## 1. 背景与目标

现有问题：
1. 视频上传到素材库时，只记录了 `file_size`，未识别 `duration`
2. `/postVideo` 发布接口未做视频时长/大小校验，会触发平台端失败
3. 存量素材数据 `duration=0`，即使上传了新视频也拿不到元数据
4. 前端必填字段标识缺失，用户无法直观判断哪些是必填
5. 部分渠道存在无用的表单字段（草稿模式、群聊、AI内容生成 等）

**目标：**
- ✅ 视频上传时自动识别 duration 写入素材库
- ✅ 视频发布前/中双重校验时长 + 大小（前端 + 后端）
- ✅ 存量数据选中时同步识别补全
- ✅ 必填字段 label 加红色 `*`
- ✅ 清理各渠道无用表单字段

---

## 2. 校验规则定义（单点来源）

新建 `backend/util/video_limits.py`，作为前后端共用的规则数据源（前端镜像一份用于 UI 提示）。

```python
# 单位：秒 / bytes
VIDEO_LIMITS = {
    "tencent_video": {"min_duration": 5,   "max_duration": 5400,    "max_size": 20 * 1024**3},  # 5s~90min,  20G
    "iqiyi":         {"min_duration": 5,   "max_duration": 3600,    "max_size": 16 * 1024**3},  # 5s~60min,  16G
    "douyin":        {"min_duration": 5,   "max_duration": 3600,    "max_size": 16 * 1024**3},  # 5s~60min,  16G
    "baijiahao":     {"min_duration": 5,   "max_duration": float("inf"), "max_size": 12 * 1024**3},  # 5s~无, 12G
    "weibo":         {"min_duration": 15,  "max_duration": float("inf"), "max_size": 15 * 1024**3},  # 15s~无, 15G
    "kuaishou":      {"min_duration": 5,   "max_duration": 3600,    "max_size": 12 * 1024**3},  # 5s~60min,  12G
    "bilibili":      {"min_duration": 5,   "max_duration": 36000,   "max_size": 16 * 1024**3},  # 5s~600min, 16G
    "xiaohongshu":   {"min_duration": 5,   "max_duration": 14400,   "max_size": 20 * 1024**3},  # 5s~240min, 20G
    "channels":      {"min_duration": 5,   "max_duration": 28800,   "max_size": 20 * 1024**3},  # 5s~480min, 20G
    "tiktok":        {"min_duration": 5,   "max_duration": 3600,    "max_size": 16 * 1024**3},  # 5s~60min,  16G
    "youtube":       {"min_duration": 5,   "max_duration": 36000,   "max_size": 16 * 1024**3},  # 5s~600min, 16G
}
```

`validate_video_for_platform(platform_key, duration_sec, size_bytes) -> (ok, error_msg)`：
- 错误消息前缀带平台中文名 + 时长（mm:ss）+ 大小（自适应 KB/MB/GB）
- 例：`"腾讯视频：时长 30 秒超出范围 (5秒 ~ 90分钟)；大小 25.3G 超出限制 (最大 20G)"`

---

## 3. 后端实现

### 3.1 视频时长识别（扩展 ffmpeg_service）

`backend/services/ffmpeg_service.py` 新增 `get_video_duration_safe(path)`：
- 优先调用现有 `get_video_duration()`（用 ffprobe，0.05s 内返回）
- ffprobe 不可用 / 失败时，fallback 到 `ffmpeg -i` 解析 stderr 中 `Duration: HH:MM:SS.xx` 行
- 都失败返回 `0.0`，记 warning 日志

**为什么不全用 ffmpeg -i：**
- ffprobe 不解码，仅读容器 metadata，毫秒级返回
- ffmpeg -i 会触发完整的 demux + stream 解析，开销略大
- 但作为 fallback 仍可接受（耗时 < 0.5s）

### 3.2 上传时识别（materials_bp.upload）

`backend/blueprints/materials_bp.py` 的 `/upload` 在写库后：
```python
if file_type == "video":
    duration = get_video_duration_safe(abs_source)
    conn.execute("UPDATE materials SET duration = ? WHERE id = ?", (duration, file_id))
```
异步后台线程跑（不阻塞上传响应）。

### 3.3 存量补全接口（新增）

`POST /api/materials/<id>/probe`：
```python
@materials_bp.route("/<material_id>/probe", methods=["POST"])
def probe(material_id):
    """识别存量视频元数据并写库，返回最新记录。"""
    row = get material by id
    if not row or row["file_type"] != "video":
        return 400/404
    abs_path = resolve_material_path(row["stored_path"])
    duration = get_video_duration_safe(abs_path)
    size = os.path.getsize(abs_path)
    UPDATE materials SET duration=?, file_size=? WHERE id=?
    return updated row + url
```

**时机：** MaterialSelectDialog 选中 video 类型素材时同步调用，spinner ~1s。

### 3.4 发布前校验（app.py:postVideo）

在 `platform.publish_video` 调用之前：
```python
# video_publish_video 的 video files 解析后
video_files = [f for f in file_list if f and f.lower().endswith(VIDEO_EXTS)]
if video_files:
    platform_key = platform.platform_key  # 例如 "tencent_video"
    mat = get_material_by_path(video_files[0])  # 复用 _resolve_material_path 反查
    if mat:
        ok, err = validate_video_for_platform(platform_key, mat["duration"], mat["file_size"])
        if not ok:
            return jsonify({"code": 400, "msg": err}), 400
```

**注意：**
- 只校验第一个视频文件（与 publish_video 实现一致）
- `get_material_by_path` 通过 `stored_path` 反查 materials 表
- 找不到材料记录时（兼容老路径直接上传）→ 跳过校验，依赖平台端

同样在 `postVideoBatch` 也加上。

---

## 4. 前端实现

### 4.1 校验规则镜像

`frontend/src/config/videoLimits.js`：
```js
export const VIDEO_LIMITS = { /* 同后端结构 */ }
export function validateVideoForPlatform(platformKey, durationSec, sizeBytes) { /* 同算法 */ }
```

### 4.2 视频对象扩展

`PublishCenter.vue` 中 `videoData` 对象补充字段：
```js
{
  id, name, url, stored_path, size: d.file_size, type: d.mime_type,
  duration: d.duration,  // 新增
}
```

### 4.3 MaterialSelectDialog 同步补全

`onSelect` 钩子：
```js
async function selectMaterial(mat) {
  if (mat.file_type === 'video' && (!mat.duration || mat.duration === 0)) {
    loading.value = true
    try {
      const res = await materialProbe(mat.id)  // 调 /probe
      mat.duration = res.duration
      mat.file_size = res.file_size
    } finally {
      loading.value = false
    }
  }
  emit('select', mat)
}
```

### 4.4 发布前校验

`PublishCenter.vue:publishAll` 入口（accountGroups 循环内）：
```js
const video = effectiveVideo(videoFormat)
if (video) {
  const ok = validateVideoForPlatform(platform.key, video.duration, video.size)
  if (!ok) {
    errors.push({ account: `${account.name}(${platform.name})`, reason: ok.err })
  }
}
```

错误聚合到已有的 `ElMessageBox.alert(errors.join('\n'))` 弹窗。

### 4.5 必填样式

`platforms.js` 的 `settingsFields` 元素加 `required: true`：
```js
{ key: 'creationDeclaration', label: '创作声明', required: true, ... }
```

`PublishCenter.vue` 渲染 settingsFields 处（line ~245）：
```vue
<div class="setting-label" :style="{ color: currentPlatformConfig.color }">
  <span v-if="field.required" style="color: #f56c6c; margin-right: 2px;">*</span>
  {{ field.label }}
</div>
```

不修改卡片边框、不加红色背景，保持视觉简洁（用户已确认）。

### 4.6 必填规则表（补全）

`PublishCenter.vue:DECLARATION_PLATFORMS` 当前缺 tiktok/weibo，按用户需求补：
```js
const DECLARATION_PLATFORMS = {
  xiaohongshu: 'aiContent',          // 内容类型声明
  douyin: 'aiContent',               // 自主声明
  kuaishou: 'aiContent',             // 作者声明
  bilibili: 'creationDeclaration',   // 创作声明
  baijiahao: 'creationDeclaration',  // 必选声明
  tencent_video: 'creationDeclaration', // 创作声明
  iqiyi: 'creationDeclaration',      // 创作声明
  youtube: ['audience', 'alteredContent'], // 观众、加工的内容
  tiktok: 'aiContent',               // AI生成内容
  weibo: 'contentStatement',         // 内容声明
  // channels: 无必填（已确认）
}
```

校验时布尔字段（`aiContent: false`）算已填：当前 `isEmpty` 判断只对 null/undefined 触发，符合预期。

### 4.7 删除无用字段

修改 `frontend/src/config/platforms.js` 的 `settingsFields`：

| 渠道 | 删除字段 |
|------|----------|
| 百家号 | `aiContent`（开关） |
| B站 | `topic`（话题） |
| 小红书 | `collection`（合集）, `groupChat`（群聊）, `location`（位置） |
| 视频号 | `isDraft`（草稿模式）, `location`（位置）, `aiContent`（AI内容生成） |

同步修改 `PublishCenter.vue` 的 `platformConfigs` reactive，删除对应字段初始化：
- xiaohongshu: 删 `collection, groupChat, location`
- bilibili: 删 `topic`
- baijiahao: 删 `aiContent`（注意：抖音、其他平台保留）
- channels: 删 `isDraft, location, aiContent`

**双重清理**避免：
- `form[field.key]` 在账号覆写恢复时残留旧数据
- watch([selectedPlatform, selectedAccountId]) 的 form 同步逻辑漏字段

---

## 5. 数据流图

```
┌────────────────────────────────────────────────────────────┐
│ 用户上传视频                                                │
│   ↓                                                         │
│ POST /api/materials/upload (multipart)                     │
│   ↓                                                         │
│ 流式写盘 → INSERT materials(file_size=total)               │
│   ↓ async                                                   │
│ get_video_duration_safe()                                  │
│   ↓                                                         │
│ UPDATE materials SET duration=?                            │
│   ↓ async                                                   │
│ _generate_video_thumbnail() (抽封面图, 已有)                │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 用户从素材库选择视频                                         │
│   ↓                                                         │
│ MaterialSelectDialog.onSelect(mat)                          │
│   ↓ (mat.duration === 0 时)                                  │
│ POST /api/materials/<id>/probe                              │
│   ↓                                                         │
│ get_video_duration_safe() + os.path.getsize()               │
│   ↓                                                         │
│ UPDATE materials SET duration=?, file_size=?                │
│   ↓ return updated row                                      │
│ emit('select', mat with duration/size)                      │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 用户点击"一键发布"                                          │
│   ↓                                                         │
│ PublishCenter.publishAll()                                  │
│   ↓ per account/per platform                                │
│ 前端校验：必填声明 + 视频时长/大小                          │
│   ↓                                                         │
│ 失败 → ElMessageBox.alert(errors.join('\n'))                │
│   ↓ 通过                                                    │
│ POST /postVideo { type, fileList, ... }                     │
│   ↓ server                                                  │
│ postVideo() → resolve_material_path() 反查 materials       │
│   ↓                                                         │
│ validate_video_for_platform()                               │
│   ↓                                                         │
│ 失败 → 400 {msg}                                            │
│   ↓ 通过                                                    │
│ platform.publish_video(...)                                 │
└────────────────────────────────────────────────────────────┘
```

---

## 6. 测试策略

### 6.1 后端
- `backend/tests/test_video_limits.py`（新文件）：
  - 11 个平台，每个平台测：下限、上限、正常范围、超时、超大、超小
  - `get_video_duration_safe`：mock 损坏 ffprobe、mock ffmpeg -i 输出
- 手动：上传 30s 视频 → 看 DB 中 `duration=30.0`
- 手动：postVideo 传入 120s 视频到 tencent_video → 应返回 400

### 6.2 前端
- `MaterialSelectDialog`：存量素材（duration=0）选中后 duration 更新
- `PublishCenter`：必填字段 label 显示 `*`
- `PublishCenter`：选 30s 视频 → 抖音 → publishAll 失败提示
- Playwright：参考 `frontend/e2e/` 已有测试

### 6.3 端到端
- 通过 `/qa` 流程验证：登录 → 上传 → 选择 → 必填 → 发布

---

## 7. 影响范围

**新增文件：**
- `backend/util/video_limits.py`
- `backend/tests/test_video_limits.py`
- `frontend/src/config/videoLimits.js`

**修改文件：**
- `backend/services/ffmpeg_service.py`（新增 `get_video_duration_safe`）
- `backend/blueprints/materials_bp.py`（upload 写 duration；新增 /probe 端点）
- `backend/app.py`（postVideo + postVideoBatch 加校验）
- `frontend/src/views/PublishCenter.vue`（DECLARATION_PLATFORMS 补全；publishAll 加校验；必填 `*` 渲染；platformConfigs 删字段）
- `frontend/src/components/MaterialSelectDialog.vue`（onSelect 加 probe 调用）
- `frontend/src/config/platforms.js`（settingsFields 加 required；删除无用字段）

**数据库：** 不变（materials 表已有 duration/file_size 列）。

---

## 8. 风险与回滚

| 风险 | 缓解 |
|------|------|
| ffprobe/ffmpeg 都不可用 → duration=0 → 校验跳过 | 加启动自检，启动时 warn；保留原行为不阻塞业务 |
| 存量数据 probe 慢（>2s） | 进度条 + 取消按钮；超时 10s 兜底 |
| 必填字段加 * 影响视觉布局 | label 短字段加 6px padding-left |
| 删除字段导致草稿加载报错 | 草稿恢复时缺失字段用 defaultSettings 兜底 |

---

## 9. 排期建议

1. **Phase 1（基础）：** video_limits + ffmpeg_service 增强 + materials_bp 改动 + probe 端点
2. **Phase 2（后端校验）：** app.py postVideo/postVideoBatch 校验
3. **Phase 3（前端校验）：** videoLimits.js + PublishCenter 校验 + MaterialSelectDialog 补全
4. **Phase 4（UI）：** 必填样式 + 删除字段
5. **Phase 5（测试）：** 单测 + Playwright + e2e

每个 Phase 可独立 commit 和部署。