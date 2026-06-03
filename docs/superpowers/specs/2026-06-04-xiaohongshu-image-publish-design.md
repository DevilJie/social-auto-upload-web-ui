# 小红书图文发布功能设计文档

## 概述

实现小红书平台的图文发布功能，复用现有的视频发布私有方法，支持标题、描述、标签、原创声明、内容类型声明、定时发布等功能。

## 背景

- 小红书平台目前只实现了视频发布（`publish_video`），图文发布会抛出 `NotImplementedError`
- 抖音和快手都已实现完整的图文发布功能，可以作为参考
- 小红书视频发布有可复用的方法：`_fill_title`、`_fill_desc`、`_fill_tags`、`_set_content_declaration`、`_set_original_declaration`、`_click_publish_button`
- 前端已有小红书 `ImagePublishPanel.vue`，但需要补充渠道级配置

## 需求

### 功能需求

1. **图片上传**：支持上传多张图片到小红书图文发布页面
2. **标题填写**：最多20字，复用现有 `_fill_title` 方法
3. **描述填写**：最多1000字，复用现有 `_fill_desc` 方法
4. **标签添加**：最多10个，复用现有 `_fill_tags` 方法
5. **原创声明**：复用现有 `_set_original_declaration` 方法
6. **内容类型声明**：复用现有 `_set_content_declaration` 方法
7. **定时发布**：支持用户指定发布时间
8. **发布按钮**：复用现有 `_click_publish_button` 方法

### 非功能需求

- 不需要封面设置
- 不需要音乐选择功能
- 保持与抖音、快手一致的代码风格

## 技术方案

### 方案选择

**方案1：直接复用现有私有方法（选定）**

在小红书平台类中直接实现 `publish_image` 方法，复用现有的私有方法。

**优点：**
- 实现简单快速，与现有代码风格一致
- 不需要修改现有代码结构
- 风险最低

**缺点：**
- 没有真正提取公共方法，其他平台无法复用
- 如果未来需要修改标题填写逻辑，需要在多个地方修改

**工作量：** 约 1-2 小时

---

## 详细设计

### 1. 后端实现

**文件：** `backend/impl/xiaohongshu/platform.py`

在 `XiaohongshuPlatform` 类中新增 `publish_image` 方法：

```python
async def publish_image(self, **kwargs) -> bool:
    """
    小红书图文发布
    
    参数：
    - title (str): 标题，最多20字
    - files (list[str]): 图片文件路径列表
    - tags (list[str]): 标签列表，最多10个
    - account_file (list[str]): Cookie文件名
    - desc (str): 描述，最多1000字
    - enableTimer (bool): 是否启用定时发布
    - schedule_time_str (str): 定时发布时间
    - ai_content (str): 内容类型声明
    - dry_run (bool): 是否模拟发布，默认True
    
    返回：
    - bool: 发布是否成功
    """
```

#### 实现步骤

1. **导航到图文发布页面**
   - URL: `https://creator.xiaohongshu.com/publish/publish?from=menu&target=image`
   - 等待页面加载完成

2. **上传图片**
   - 使用 `page.set_input_files` 上传多张图片
   - 等待图片上传完成
   - 新增私有方法：`_upload_images(page, files)`

3. **填写标题**
   - 复用 `_fill_title(page, title)` 方法
   - 最多20字，超出部分截断

4. **填写描述**
   - 复用 `_fill_desc(page, desc)` 方法
   - 最多1000字，超出部分截断

5. **添加标签**
   - 复用 `_fill_tags(page, tags)` 方法
   - 最多10个标签，超出部分忽略

6. **设置原创声明**
   - 复用 `_set_original_declaration(page)` 方法

7. **设置内容类型声明**
   - 复用 `_set_content_declaration(page, ai_content)` 方法

8. **设置定时发布**
   - 新增私有方法：`_set_schedule_time(page, enableTimer, schedule_time_str)`
   - 如果 `enableTimer` 为 True，设置发布时间
   - 如果 `schedule_time_str` 为空，使用默认时间（明天同一时间）

9. **点击发布**
   - 复用 `_click_publish_button(page, "发布")` 方法
   - 等待发布完成
   - 如果 `dry_run` 为 True，不实际点击发布

#### 新增私有方法

```python
async def _upload_images(self, page, files: list[str]) -> bool:
    """
    上传图片到图文发布页面
    
    参数：
    - page: Playwright page 对象
    - files: 图片文件路径列表
    
    返回：
    - bool: 上传是否成功
    """
    # 实现图片上传逻辑
    pass

async def _set_schedule_time(self, page, enableTimer: bool, schedule_time_str: str) -> bool:
    """
    设置定时发布时间
    
    参数：
    - page: Playwright page 对象
    - enableTimer: 是否启用定时发布
    - schedule_time_str: 定时发布时间字符串
    
    返回：
    - bool: 设置是否成功
    """
    # 实现定时发布时间设置逻辑
    pass
```

---

### 2. 前端配置

**文件：** `frontend/src/config/platforms.js`

更新小红书（XIAOHONGSHU）配置，添加渠道级设置：

```javascript
XIAOHONGSHU: {
  // ... 现有配置
  settings: {
    // ... 现有设置
    scheduleTime: {
      type: 'datetime',
      label: '定时发布',
      placeholder: '选择发布时间',
      required: false
    }
  }
}
```

**文件：** `frontend/src/components/xiaohongshu/ImagePublishPanel.vue`

更新面板组件，添加定时发布控件：
- 添加定时发布开关
- 添加时间选择器
- 保持现有的标题、描述、标签控件

---

### 3. 数据流

```
前端 ImagePublishPanel.vue
    ↓
imagePublishApi.publishImage()
    ↓
后端 /api/image-publish/publish
    ↓
XiaohongshuPlatform.publish_image()
    ↓
复用现有私有方法 + 新增方法
    ↓
小红书创作者中心
```

---

### 4. 错误处理

- **图片上传失败**：记录日志，返回 False
- **标题/描述超长**：截断并记录警告
- **标签超限**：只取前10个
- **定时时间无效**：使用默认时间
- **网络异常**：重试3次后失败

---

### 5. 测试策略

#### 单元测试

- 测试参数验证
- 测试标签截断逻辑
- 测试定时时间解析

#### 集成测试

- 测试完整的发布流程（dry_run=True）
- 测试多账号发布

#### 手动测试

- 在小红书创作者中心实际测试
- 验证标题、描述、标签、原创声明、内容类型声明、定时发布功能

---

## 时间估算

| 任务 | 预计时间 |
|------|----------|
| 后端实现（publish_image + 新增方法） | 1 小时 |
| 前端配置更新 | 30 分钟 |
| 测试验证 | 30 分钟 |
| **总计** | **2 小时** |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 小红书页面结构变化 | 功能失效 | 使用稳定的 CSS 选择器，添加错误处理 |
| 图片上传失败 | 发布失败 | 重试机制，记录详细日志 |
| 定时发布时间格式不兼容 | 定时失败 | 使用现有的 `parse_schedule_time` 函数 |

---

## 后续优化

1. **提取公共方法**：将标题、描述、标签等公共功能提取到独立模块
2. **支持更多功能**：音乐选择、封面设置等
3. **性能优化**：并行上传图片，减少等待时间

---

## 参考资料

- 抖音图文发布实现：`backend/impl/douyin/platform.py` (line 698)
- 快手图文发布实现：`backend/impl/kuaishou/platform.py` (line 228)
- 小红书视频发布实现：`backend/impl/xiaohongshu/platform.py` (line 208)
- 统一发布接口：`backend/blueprints/image_publish_bp.py`
