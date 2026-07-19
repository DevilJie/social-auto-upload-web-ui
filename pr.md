# PR: feat(v1.2.2) VIVO 平台接入 + 封面系统重构 + 10 平台稳定性修复

## 概述

本次发布 16 个平台版 VIVO 内容创作平台正式接入，封面系统全面重构（4:3/16:9/3:4/9:16 多比例可设，不再污染素材库），账号运营数据（粉丝/获赞/关注）字段落地，并修复抖音/视频号/支付宝/B 站/百家号/快手/知乎/腾讯视频/头条 9 个平台的关键 Bug。

---

## PR 类型

- [x] 新功能（VIVO 平台接入、账号运营数据、封面系统重构、新增赞助页面）
- [x] Bug 修复（10 个平台 bug + 发布历史封面图 + 个性化选视频 bug + 浏览器关闭智能识别）
- [x] 工程效率（util/_logger 修复 csdn/vivo 日志路由历史 bug）
- [x] 文档（v1.2.2 更新日志）

---

## 核心变更

### 1. VIVO 内容创作平台接入（`backend/impl/vivo/`）

新增 `VivoPlatform`（platform_id=16），继承 `BasePlatform`，注册到 `registry.py`：

- **创作者中心**：`https://www.kaixinkan.com.cn/#/home`
- **视频发布**：`https://www.kaixinkan.com.cn/#/content/uploads`
- **规范**：视频大小≤2G、时长≤90min、描述≤500字
- **完整发布流程**：
  1. 扫码登录（可见浏览器 + 轮询 `.user-info-area` 出现判定成功）
  2. 资料同步（昵称/头像/粉丝/获赞，关注固定 0）
  3. 上传视频文件（`input[type=file]`，轮询 `.success-text:has-text("上传成功")`，**4 小时超时**）
  4. 描述+标签（contenteditable 逐字符输入；`#xxx` 末尾空格激活话题）
  5. 3:4 竖版封面（点编辑封面 → 切上传 tab → 上传 → 处理裁剪 → div 确定）
  6. 位置（`.sel-position-module` → 输入关键词 → 解析 `.position-list li`）
  7. 作品同步（`label.el-checkbox` 文案定位勾选）
  8. 自主声明（`div.el-select-dropdown__item` 文案匹配）
  9. 谁可以看 / 下载权限（radio by label + option text）
  10. 定时发布（直接 fill 两个文本框：yyyy-MM-dd + HH:mm）
  11. 提交 → URL 跳转判定成功
- **严格遵守**：所有 selector 用产品语义 class（`.user-info-area` / `.cover-photo-img` / `.sel-position-module` 等），**禁用 `data-v-xxx` 随机字符串**

### 2. 账号运营数据（粉丝 / 获赞 / 关注）

- `user_info` 表新增 `fans/likes/follows` 三列（幂等迁移，默认 0）
- `BasePlatform.sync_profile` 约定支持 5 元组返回（向后兼容 2 元组）：
  - 2 元组 `(name, avatar)` — 旧平台
  - 5 元组 `(name, avatar, fans, likes, follows)` — 新平台（如 VIVO）
- `save_login_result` / `syncProfile` 路由 / `setAccounts` store 全部按元组长度兼容解包写库
- 前端账号卡片底部展示「粉丝 N · 获赞 N · 关注 N」，其余平台字段保留为 0 待后续版本接入

### 3. VIVO 位置搜索自动化（`/api/vivo/search-position`）

- 仿 `xiaohongshu_bp.py` 模式：浏览器自动化打开 VIVO 发布页 → 上传测试视频触发表单 → 在 `.sel-position-module` 输入关键词 → 解析 `.position-list li` 的 `.position-name` + `.position-info`
- 前端 `VivoPositionSelect.vue` 复用模式与小红书 POI 一致，空值即不显示位置

### 4. 封面系统全面重构

- **封面不再保存到素材库**（避免占用不必要资源），改为临时处理
- 4:3 / 16:9 / 3:4 / 9:16 四种比例可按视频方向自动选择
- 头条 / 腾讯视频 / 知乎 / 视频号 / 快手 已按方向自动选择新尺寸
- CSDN 固定横版、百家号固定横竖各一
- 爱奇艺封面弹窗新增 16:9 横封面 tab
- 封面弹窗尺寸 tab 改造 + 布局重设计 + 亮色样式修复
- 封面裁剪改为两个独立面板，确认时统一校验裁剪结果

### 5. 10 个平台稳定性修复

| 平台 | 修复内容 |
|---|---|
| 抖音 | 定时发布时间丢失 → Semi 时间滚轮选时/分 |
| 视频号 | 封面遍历所有入口 + 横版封面 popover 处理 |
| 支付宝 | 作者声明 radio 改点 label（antd5 受控组件）；新增转载来源联动 |
| B 站 | 创作声明=转载时新增必填转载来源 |
| 百家号 | 固定 16:9 横版 + 3:4 竖版 |
| 快手 | 视频封面前按方向选裁剪比例 |
| 知乎 | 横版视频优先 16:9 封面 |
| 腾讯视频 | 封面按方向 + UploadNotify 4h 超时 + 永远等的 formTitle 移除 |
| 头条 | 封面按方向选 16:9/9:16 + 二次确认弹窗精确点确定按钮 |
| 全平台 | 浏览器关闭智能识别（disarm 标志），手动关浏览器不再卡死 |

### 6. 体验优化

- 亮色模式账号选中字体改用品牌紫，亮色下不再发白看不清
- 勾选账号个性化后首次从素材库选视频不显示（`getMergedSettings` filter 漏过滤 null 修复）
- 发布历史封面图显示修复（`_resolve_cover_from_path` 修复 `covers/` 前缀路径）
- 新增赞助作者页面（侧边栏底部品牌色菜单 + 支付宝/微信收款码 + 顶部徽章心跳红点）

### 7. 工程效率

- `util/_logger.CHANNELS` 补全 csdn + vivo，修复日志路由缺失历史 bug（csdn 平台之前的日志也丢了）

---

## 涉及文件

```
后端新增(3 个):
  backend/impl/vivo/__init__.py
  backend/impl/vivo/platform.py            (540 行)
  backend/blueprints/vivo_bp.py            (167 行)

后端修改(10 个):
  backend/init_db.py                       user_info 新增 3 列迁移
  backend/impl/base_platform.py            sync_profile 文档说明 5 元组
  backend/impl/_utils.py                   scrape_vivo_profile + save_login_result 兼容
  backend/impl/registry.py                 注册 VivoPlatform
  backend/util/_logger.py                  CHANNELS 补 csdn+vivo
  backend/util/video_limits.py             vivo 校验规则
  backend/app.py                           PLATFORM_MAP + blueprint + publish kwargs
  backend/ext_api/__init__.py              硬编码字典补 vivo (修草稿箱显示)
  backend/blueprints/image_publish_bp.py   platform_map 补 vivo

前端新增(3 个):
  frontend/src/api/vivo.js
  frontend/src/components/vivo/PositionSelect.vue
  frontend/src/assets/logos/vivo.svg       (3.4KB, Vite 内联到 bundle)

前端修改(6 个):
  frontend/src/config/platforms.js         VIVO 配置
  frontend/src/config/videoLimits.js      vivo 镜像规则
  frontend/src/stores/account.js           索引偏移适配
  frontend/src/views/AccountManagement.vue 账号卡片显示粉丝/获赞/关注
  frontend/src/views/PublishCenter.vue     集成 + poiSelect 分流
  frontend/src/components/PrePublishCheckDialog.vue  platformTypeToKey

文档 + 资源:
  versions                                 1.2.1 → 1.2.2
  changelog/20260719.html                  v1.2.2 更新日志页面
  frontend/src/assets/alipay.jpg + weixin.jpg  赞助页面收款码
```

---

## 验证

- ✅ 后端 Python 语法 OK
- ✅ VIVO 平台通过 registry 成功加载（platform_id=16）
- ✅ scrape_vivo_profile / PLATFORM_SYNC_URLS / VIDEO_LIMITS 注册正确
- ✅ 数据库迁移成功（3 列添加，幂等无报错）
- ✅ 前端 `npm run build` 成功（18.82s）
- ✅ vivo.svg 内联为 data URI 进入 bundle
- ✅ 实际登录/扫码流程验证通过
- ✅ 实际视频发布流程（dry_run 模式）验证通过：描述+标签+封面+位置+作品同步+自主声明+定时发布 全部正常填写
- ✅ 草稿箱显示「VIVO」+ vivo 图标（修复「平台16」问题）

## 兼容性

- ✅ 旧平台 sync_profile 返回 2 元组仍正常工作（save_login_result / syncProfile 路由按元组长度兼容解包）
- ✅ 账号 store.setAccounts 按新列顺序索引映射（id/type/filePath/userName/status/avatar/fans/likes/follows/tags），向后兼容
- ✅ logger CHANNELS 补全后，csdn 平台日志也恢复正常（顺带修复历史 bug）

---

**37 个提交 · 104 文件 · 9774 行新增**
