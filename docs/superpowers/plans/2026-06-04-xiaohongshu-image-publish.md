# 小红书图文发布功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现小红书平台的图文发布功能，复用现有的视频发布私有方法

**Architecture:** 在 XiaohongshuPlatform 类中新增 publish_image 方法，复用 _fill_title、_fill_desc、_fill_tags、_set_schedule_time、_set_content_declaration、_set_original_declaration、_click_publish_button 等私有方法。前端面板补充定时发布、原创声明、内容类型声明字段。

**Tech Stack:** Python, Playwright, Vue 3, Element Plus

---

## 文件结构

### 后端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/impl/xiaohongshu/platform.py` | 修改 | 新增 publish_image 方法和 _upload_images 私有方法 |

### 前端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/components/xiaohongshu/ImagePublishPanel.vue` | 修改 | 添加定时发布、原创声明、内容类型声明字段 |

---

## Task 1: 后端 - 新增图文发布URL常量

**Files:**
- Modify: `backend/impl/xiaohongshu/platform.py`

- [ ] **Step 1: 查看现有常量定义**

```bash
grep -n "_XHS_PUBLISH" backend/impl/xiaohongshu/platform.py
```

Expected: 找到 `_XHS_PUBLISH_VIDEO_URL` 常量定义

- [ ] **Step 2: 新增图文发布URL常量**

在 `_XHS_PUBLISH_VIDEO_URL` 常量后面添加：

```python
_XHS_PUBLISH_IMAGE_URL = "https://creator.xiaohongshu.com/publish/publish?from=menu&target=image"
```

- [ ] **Step 3: 验证常量已添加**

```bash
grep -n "_XHS_PUBLISH_IMAGE_URL" backend/impl/xiaohongshu/platform.py
```

Expected: 找到新添加的常量

- [ ] **Step 4: Commit**

```bash
git add backend/impl/xiaohongshu/platform.py
git commit -m "feat(小红书): 新增图文发布URL常量"
```

---

## Task 2: 后端 - 实现 _upload_images 私有方法

**Files:**
- Modify: `backend/impl/xiaohongshu/platform.py`

- [ ] **Step 1: 查看现有私有方法结构**

```bash
grep -n "async def _" backend/impl/xiaohongshu/platform.py
```

Expected: 找到现有的私有方法列表

- [ ] **Step 2: 实现 _upload_images 方法**

在 `_set_thumbnail` 方法后面添加：

```python
async def _upload_images(page, files: list[str]) -> bool:
    """
    上传图片到图文发布页面
    
    参数：
    - page: Playwright page 对象
    - files: 图片文件路径列表
    
    返回：
    - bool: 上传是否成功
    """
    try:
        # 等待图片上传输入框出现
        upload_input = await page.wait_for_selector(
            'input[type="file"][accept*="image"]',
            timeout=10000
        )
        
        # 上传所有图片
        await upload_input.set_input_files(files)
        
        # 等待图片上传完成（检查图片数量）
        expected_count = len(files)
        for i in range(30):  # 最多等待30秒
            uploaded = await page.query_selector_all('div[class*="upload"] img')
            if len(uploaded) >= expected_count:
                return True
            await asyncio.sleep(1)
        
        logger.warning(f"图片上传超时，已上传 {len(uploaded)}/{expected_count}")
        return len(uploaded) > 0
        
    except Exception as e:
        logger.error(f"图片上传失败: {e}")
        return False
```

- [ ] **Step 3: 验证方法已添加**

```bash
grep -n "_upload_images" backend/impl/xiaohongshu/platform.py
```

Expected: 找到新添加的方法

- [ ] **Step 4: Commit**

```bash
git add backend/impl/xiaohongshu/platform.py
git commit -m "feat(小红书): 新增 _upload_images 图片上传方法"
```

---

## Task 3: 后端 - 实现 publish_image 方法骨架

**Files:**
- Modify: `backend/impl/xiaohongshu/platform.py`

- [ ] **Step 1: 查看 publish_video 方法结构**

```bash
grep -n "def publish_video" backend/impl/xiaohongshu/platform.py
```

Expected: 找到 publish_video 方法定义

- [ ] **Step 2: 实现 publish_image 方法骨架**

在 publish_video 方法后面添加：

```python
def publish_image(self, **kwargs) -> bool:
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
    title = kwargs.get('title', '')
    files = kwargs.get('files', [])
    tags = kwargs.get('tags', [])[:10]  # 最多10个标签
    account_file = kwargs.get('account_file', [])
    desc = kwargs.get('desc', '')[:1000]  # 最多1000字
    enableTimer = kwargs.get('enableTimer', False)
    schedule_time_str = kwargs.get('schedule_time_str', '')
    ai_content = kwargs.get('ai_content', '')
    dry_run = kwargs.get('dry_run', True)
    
    if not files:
        logger.error("没有图片文件")
        return False
    
    if not account_file:
        logger.error("没有账号文件")
        return False
    
    # 截断标题
    title = title[:20]
    
    success_count = 0
    for account in account_file:
        try:
            result = asyncio.run(self._publish_single_image(
                title=title,
                files=files,
                tags=tags,
                account_file=account,
                desc=desc,
                enableTimer=enableTimer,
                schedule_time_str=schedule_time_str,
                ai_content=ai_content,
                dry_run=dry_run
            ))
            if result:
                success_count += 1
        except Exception as e:
            logger.error(f"账号 {account} 发布失败: {e}")
    
    return success_count > 0
```

- [ ] **Step 3: 验证方法已添加**

```bash
grep -n "def publish_image" backend/impl/xiaohongshu/platform.py
```

Expected: 找到新添加的方法

- [ ] **Step 4: Commit**

```bash
git add backend/impl/xiaohongshu/platform.py
git commit -m "feat(小红书): 新增 publish_image 方法骨架"
```

---

## Task 4: 后端 - 实现 _publish_single_image 方法

**Files:**
- Modify: `backend/impl/xiaohongshu/platform.py`

- [ ] **Step 1: 查看 _publish_single_video 方法结构**

```bash
grep -n "async def _publish_single_video" backend/impl/xiaohongshu/platform.py
```

Expected: 找到 _publish_single_video 方法定义

- [ ] **Step 2: 实现 _publish_single_image 方法**

在 _publish_single_video 方法后面添加：

```python
async def _publish_single_image(self, title, files, tags, account_file, desc, 
                                enableTimer, schedule_time_str, ai_content, dry_run):
    """
    发布单个图文笔记
    
    参数：
    - title: 标题
    - files: 图片文件路径列表
    - tags: 标签列表
    - account_file: Cookie文件名
    - desc: 描述
    - enableTimer: 是否启用定时发布
    - schedule_time_str: 定时发布时间
    - ai_content: 内容类型声明
    - dry_run: 是否模拟发布
    
    返回：
    - bool: 发布是否成功
    """
    from backend.impl._browser import CloakBrowser
    
    browser = CloakBrowser()
    try:
        # 创建浏览器上下文
        context = await browser.create_context(account_file)
        page = await context.new_page()
        
        # 导航到图文发布页面
        await page.goto(_XHS_PUBLISH_IMAGE_URL, wait_until='networkidle')
        
        # 上传图片
        if not await _upload_images(page, files):
            logger.error("图片上传失败")
            return False
        
        # 等待页面就绪
        await asyncio.sleep(2)
        
        # 填写标题
        await _fill_title(page, title)
        
        # 填写描述
        await _fill_desc(page, desc)
        
        # 添加标签
        await _fill_tags(page, tags)
        
        # 设置原创声明
        await _set_original_declaration(page)
        
        # 设置内容类型声明
        if ai_content:
            await _set_content_declaration(page, ai_content)
        
        # 设置定时发布
        if enableTimer:
            await _set_schedule_time(page, schedule_time_str)
        
        # 等待页面就绪
        await _wait_for_page_ready(page)
        
        # 点击发布
        if not dry_run:
            await _click_publish_button(page, "发布")
            await asyncio.sleep(3)
            logger.info(f"图文发布成功: {title}")
        else:
            logger.info(f"图文发布模拟成功: {title}")
        
        # 保存Cookie
        await browser.save_cookies(context, account_file)
        
        return True
        
    except Exception as e:
        logger.error(f"图文发布失败: {e}")
        return False
    finally:
        await browser.close()
```

- [ ] **Step 3: 验证方法已添加**

```bash
grep -n "async def _publish_single_image" backend/impl/xiaohongshu/platform.py
```

Expected: 找到新添加的方法

- [ ] **Step 4: Commit**

```bash
git add backend/impl/xiaohongshu/platform.py
git commit -m "feat(小红书): 新增 _publish_single_image 方法"
```

---

## Task 5: 前端 - 更新 ImagePublishPanel 添加渠道级配置

**Files:**
- Modify: `frontend/src/components/xiaohongshu/ImagePublishPanel.vue`

- [ ] **Step 1: 查看现有面板结构**

```bash
grep -n "form\." frontend/src/components/xiaohongshu/ImagePublishPanel.vue | head -20
```

Expected: 找到现有的表单字段

- [ ] **Step 2: 添加定时发布字段**

在标签输入框后面添加：

```vue
<!-- 定时发布 -->
<el-form-item label="定时发布">
  <el-switch v-model="form.enableTimer" />
  <el-date-picker
    v-if="form.enableTimer"
    v-model="form.scheduleTime"
    type="datetime"
    placeholder="选择发布时间"
    style="margin-left: 10px;"
  />
</el-form-item>

<!-- 原创声明 -->
<el-form-item label="原创声明">
  <el-switch v-model="form.isOriginal" />
</el-form-item>

<!-- 内容类型声明 -->
<el-form-item label="内容类型声明">
  <el-select v-model="form.aiContent" placeholder="请选择">
    <el-option label="无" value="" />
    <el-option label="AI生成" value="AI生成" />
    <el-option label="个人观点" value="个人观点" />
    <el-option label="转载" value="转载" />
    <el-option label="营销推广" value="营销推广" />
    <el-option label="虚构演绎" value="虚构演绎" />
  </el-select>
</el-form-item>
```

- [ ] **Step 3: 更新 XHS_DEFAULTS 添加新字段**

```javascript
const XHS_DEFAULTS = {
  ...PLATFORMS.XIAOHONGSHU.defaultSettings,
  tags: [],
  enableTimer: false,
  isOriginal: false,
}
```

- [ ] **Step 4: 更新 publishFn 传递新字段**

```javascript
publishFn: async (accountId, accountName, commonData, merged) => {
  const account = accountStore.accounts.find(a => a.id === accountId)
  await imagePublishApi.publishImage({
    image_ids: commonData.images.map(img => img.id),
    account_configs: [{
      account_id: accountId,
      platform: account.platform,
      filePath: account.filePath,
      title: merged.title,
      description: merged.description || '',
      tags: merged.tags || [],
      scheduleTime: merged.enableTimer ? merged.scheduleTime : '',
      aiContent: merged.aiContent || '',
      isOriginal: merged.isOriginal || false,
      cover_path: commonData.coverImage?.stored_path || '',
      dry_run: false,
    }],
  })
}
```

- [ ] **Step 5: 验证前端编译**

```bash
cd frontend && npm run build
```

Expected: 编译成功，无错误

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/xiaohongshu/ImagePublishPanel.vue
git commit -m "feat(小红书): ImagePublishPanel 添加定时发布/原创声明/内容类型声明"
```

---

## Task 6: 集成测试 - 验证图文发布流程

**Files:**
- Test: 手动测试

- [ ] **Step 1: 启动后端服务**

```bash
cd backend && python3 app.py
```

Expected: 服务启动成功，监听 5409 端口

- [ ] **Step 2: 启动前端服务**

```bash
cd frontend && npm run dev
```

Expected: 服务启动成功，监听 5173 端口

- [ ] **Step 3: 测试图文发布（dry_run=True）**

1. 打开浏览器访问 http://localhost:5173
2. 进入图文发布页面
3. 选择小红书平台
4. 上传图片
5. 填写标题、描述、标签
6. 设置定时发布（可选）
7. 设置原创声明（可选）
8. 设置内容类型声明（可选）
9. 点击发布

Expected: 控制台显示"图文发布模拟成功"

- [ ] **Step 4: 测试图文发布（dry_run=False）**

重复上述步骤，但 dry_run=False

Expected: 图文成功发布到小红书

- [ ] **Step 5: Commit 测试结果**

```bash
git add .
git commit -m "test(小红书): 图文发布功能测试通过"
```

---

## 自我审查

### 1. 规范覆盖检查

- ✅ 图片上传：Task 2 实现了 _upload_images 方法
- ✅ 标题填写：复用现有 _fill_title 方法
- ✅ 描述填写：复用现有 _fill_desc 方法
- ✅ 标签添加：复用现有 _fill_tags 方法
- ✅ 原创声明：复用现有 _set_original_declaration 方法
- ✅ 内容类型声明：复用现有 _set_content_declaration 方法
- ✅ 定时发布：Task 4 实现了 _set_schedule_time 调用
- ✅ 发布按钮：复用现有 _click_publish_button 方法

### 2. 占位符扫描

- 无 TBD、TODO 或不完整的部分
- 所有代码示例都是完整的

### 3. 类型一致性

- 方法签名一致：publish_image(**kwargs) -> bool
- 参数名称一致：title, files, tags, account_file, desc, enableTimer, schedule_time_str, ai_content, dry_run
- 返回类型一致：bool

---

## 执行选择

**计划已完成并保存到 `docs/superpowers/plans/2026-06-04-xiaohongshu-image-publish.md`**

两种执行方式：

**1. Subagent-Driven（推荐）** - 每个任务分发一个新子代理，任务间进行审查，快速迭代

**2. Inline Execution** - 在当前会话中执行任务，批量执行并设置检查点

请选择执行方式？
