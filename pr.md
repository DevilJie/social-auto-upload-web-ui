# PR: feat(v1.2.3) 账号运营数据同步 + 视频号活动 + 4 项自动化修复

## 概述

本次发布聚焦 **「数据更完整 + 自动化更稳」** —— 账号列表新增 **运营数据同步**(粉丝/获赞/作品等核心指标,覆盖 10+ 平台),视频号发布页新增 **「活动」参与设置**,全局 **下拉搜索组件** 统一重构(2s 自动搜索 + 卡片式紧凑布局),并修复小红书标签、视频号最后一个标签、下拉框回车触发等多个自动化细节 Bug。

---

## PR 类型

- [x] 新功能（账号运营数据同步、视频号活动参与）
- [x] 优化（全局下拉搜索组件重构）
- [x] Bug 修复（小红书标签、视频号最后一个标签、回车触发搜索、RemoteSearchSelect 间距）

---

## 核心变更

### 1. 账号运营数据同步（10+ 平台）

账号卡片底部新增「粉丝 N · 获赞 N · 关注 N」展示，无需挨个打开平台后台查看。

- **前端**：`AccountManagement.vue` 账号卡片动态渲染运营数据；`account.js` store 扩展字段；占位提示（无数据时显示「点下方获取数据」）
- **后端**：各平台 `sync_profile` 抓取数据，存量账号无运营数据时显示占位
- **覆盖平台**：抖音、今日头条、CSDN、微博、小红书、B 站、视频号 等 10+ 平台
- **数据契约**：`user_info` 表新增 `fans/likes/follows` 三列（幂等迁移，默认 0）

### 2. 视频号「活动」参与设置（`/api/channels/activities`）

发布视频号时，可搜索并参与官方活动，获得平台流量扶持。

- **前端**：`PublishCenter.vue` 新增「活动」卡片（平台级字段，选中平台即显示，无需先选账号）
- **后端**：
  - `channels_bp.py` 新增 `/api/channels/activities?account_id=&keyword=` 路由 + `_fetch_activities_via_browser`
  - 入口 `div.post-activity-wrap`，搜索框 `input[placeholder="搜索活动"]`，选项 `.activity-item-info` 下 `.creator-name + .name`，跳过 index 0「不参与活动」
  - `app.py` /postVideo 路由补传 `channels_activity_name` + `channels_activity_id` kwargs
- **复合匹配**：按 `(name, creator_name)` 精确匹配，避免选错同名活动；`activity_id = f"{name}|{creator_name}"`
- **下拉等待**：clear_and_type 后 wait_for 真实数据出现再遍历（修法同小红书 _fill_tags）

### 3. 全局下拉搜索组件重构（`RemoteSearchSelect.vue`）

视频号位置、小红书拍摄地点、小红书合集、视频号合集等 5+ 处统一改造。

- **2s 自动搜索**：用户停止输入 2s 后自动触发（保留 Enter 立即触发）
- **卡片式布局**：每项独立卡片，背景 + 1px 边框 + hover 投影
- **紧凑调整**：margin 2/8px、padding 7/10px、单屏可见项数从 4 提升到 6+
- **line-height 1.2**：label/desc 紧凑贴合，文字之间 1px 间距
- **小红书拍摄地点**：原 PoiSelect.vue 自维护 185 行组件，重构为 RemoteSearchSelect 薄包装（39 行），统一平台风格

### 4. Bug 修复

| 平台 | 现象 | 修复 |
|---|---|---|
| 小红书 | 标签偶尔无法被识别为话题，发布后没话题标记 | 改为 wait_for 等待话题联想下拉真实出现再按 Space |
| 视频号 | 描述框连续输入多个 #tag，最后一个标签 React 处理撞车 | 每个标签后停 0.5s + 字符间隔 30ms |
| 全局 | 下拉框按回车不触发搜索，部分浏览器/键盘布局失效 | 事件绑定逻辑修复（具体见提交） |
| RemoteSearchSelect | 卡片间距、label/desc 间距、紧凑度 | 多次样式微调，平衡视觉与密度 |

### 5. 工程效率

- `app.py` /postVideo 路由补传 `channels_activity_name` kwargs（漏传导致自动化不选活动）
- `platform.py` `_apply_activity` 复合匹配 + wait_for 真实数据出现

---

## 涉及文件

```
后端修改(4 个):
  backend/app.py                          /postVideo 路由补传 channels_activity_*
  backend/blueprints/channels_bp.py       /api/channels/activities 新增
  backend/impl/channels/platform.py       _apply_activity 复合匹配 + wait_for
  backend/impl/xiaohongshu/platform.py    _fill_tags wait_for 真实数据再按 Space

前端修改(5 个):
  frontend/src/api/channels.js            searchActivities 新增
  frontend/src/api/xiaohongshu.js         (未改,searchPoi 已存在)
  frontend/src/components/common/RemoteSearchSelect.vue   自动搜索 + 卡片式紧凑布局
  frontend/src/components/xiaohongshu/PoiSelect.vue        改用 RemoteSearchSelect
  frontend/src/config/platforms.js         视频号 defaultSettings 加 channelsActivity*
  frontend/src/views/PublishCenter.vue    活动卡片 + fetcher + form merge 4 级合并

文档 + 版本:
  versions                                1.2.2 → 1.2.3
  changelog/20260721.html                 v1.2.3 更新日志页面
```

---

## 验证

- ✅ 后端 Python 语法 OK（`app.py` / `channels_bp.py` / `platform.py`）
- ✅ 前端 Vue SFC 语法 OK（`PublishCenter.vue` / `RemoteSearchSelect.vue` / `PoiSelect.vue`）
- ✅ Vite HMR 200 / 后端 5409 LISTENING
- ✅ `/api/channels/activities` 路由注册成功（之前 404 → 现 200）
- ✅ 实际发布流程验证：draft=24 草稿「畅视界 · 2026世界杯足球」活动精确选中
- ✅ 视频号最后一个标签稳定解析（多个 #tag 输入不再丢字符）
- ✅ 小红书话题标签稳定识别（wait_for 真实数据出现再按 Space）

## 兼容性

- ✅ 小红书拍摄地点改用统一组件后，发布流程完全等价（前端 form merge 4 级合并保持向后兼容）
- ✅ 视频号活动字段为新增字段，未启用时默认空（默认「不参与活动」），不影响老草稿
- ✅ RemoteSearchSelect 自动搜索可关闭（不破坏原有"必须按回车"的工作流）

---

**16 个提交 · 11 文件 · ~1100 行新增**
