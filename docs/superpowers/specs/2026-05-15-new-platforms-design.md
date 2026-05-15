# 平台整合设计：百家号 + TikTok海外版 + YouTube

**日期**: 2026-05-15
**状态**: 已批准

---

## 1. 目标

将百家号、TikTok海外版、YouTube 三个平台整合到现有社交媒体自动上传系统，与现有平台（B站、抖音、小红书、视频号、快手）保持一致的用户体验和架构模式。

---

## 2. 架构概览

```
backend/app.py → vendor/upstream/myUtils/postVideo.py
                    → uploader/{百家号|TikTok|YouTube}_uploader/
```

每个新平台遵循现有模式：
- **后端上传器**: `vendor/upstream/uploader/平台_uploader/`
- **入口函数**: `vendor/upstream/myUtils/postVideo.py` 新增 post 函数
- **前端**: `frontend/src/config/platforms.js` 新增平台配置

---

## 3. 平台ID分配

| 平台 | ID | Key | 名称 | 主题色 |
|------|-----|-----|------|--------|
| 百家号 | 6 | baijiahao | 百家号 | #e64e3a |
| TikTok海外 | 7 | tiktok | TikTok | #000000 |
| YouTube | 8 | youtube | YouTube | #ff0000 |

---

## 4. 后端改动

### 4.1 新增上传器目录

从 `vendor/upstream/` 上游代码复制以下目录：

| 平台 | 源目录 | 目标目录 |
|------|--------|----------|
| 百家号 | 上游 baijiahao_uploader | vendor/upstream/uploader/baijiahao_uploader/ |
| TikTok | 上游 tk_uploader | vendor/upstream/uploader/tk_uploader/ |
| YouTube | 上游 youtube_uploader | vendor/upstream/uploader/youtube_uploader/ |

### 4.2 新增入口函数

文件: `vendor/upstream/myUtils/postVideo.py`

新增函数:
- `post_video_baijiahao()` - 百家号发布
- `post_video_tiktok()` - TikTok海外版发布
- `post_video_youtube()` - YouTube发布

每个函数接收参数与现有函数结构一致。

### 4.3 配置更新

文件: `vendor/upstream/conf.py`

新增平台配置项（参考现有平台格式）。

---

## 5. 前端改动

### 5.1 平台配置

文件: `frontend/src/config/platforms.js`

新增平台配置对象（参考现有平台结构）:
- `BAIJIAHAO` (id: 6)
- `TIKTOK` (id: 7)
- `YOUTUBE` (id: 8)

配置内容: key, name, letter, logo (SVG), color, bgColor, settingsFields, defaultSettings

### 5.2 视图更新

| 文件 | 改动 |
|------|------|
| `PublishCenter.vue` | 平台选择器自动包含新平台 |
| `AccountManagement.vue` | 账号管理支持新平台 |

---

## 6. 认证方式

所有三个新平台统一使用 **Cookie文件上传** 方式，与现有平台保持一致。

---

## 7. 实现顺序

1. 后端上传器复制和调试（百家号 → TikTok → YouTube）
2. 入口函数对接
3. 前端平台配置
4. 视图集成
5. 联调测试

---

## 8. 参考文件

- `vendor/upstream/uploader/base_video.py` - 上传器基类
- `vendor/upstream/uploader/bilibili_uploader/main.py` - B站上传器参考
- `frontend/src/config/platforms.js` - 平台配置参考