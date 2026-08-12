# 淘宝光合「关联商品/店铺」轨迹快照改造 · 设计文档

- 日期: 2026-08-12
- 影响范围: 淘宝光合平台商品/店铺关联的前端选品、后端发布时定位勾选
- 背景提交: `dcd05f7 feat(taobao_guanghe): 集成关联商品/店铺 + 发布流程多项修复`

## 1. 背景与问题

当前实现:
- 用户在 `GuangheItemPicker` 弹窗里搜索/筛选/选品
- 确认时只把 `[{title, image}]` emit 给父组件,丢弃了 itemId 和当时的查找路径
- 发布时后端 `_link_products_or_shops` 把每个 title 填进搜索框 + 按 `span[title=name]` 精确完整匹配

问题:
- 完整商品标题(如「小米17 Pro 16GB+512GB 骁龙8 Gen4 ...」)在光合面板搜索框里经常搜不到结果
- 即使搜到,`span[title]` 完整字符串匹配容易因空格/特殊字符/截断失败

## 2. 目标

让用户在选品时记录每个商品的「查找轨迹」(搜索词/筛选规则/品类/tab),发布时后端按轨迹重现路径,并用稳定的 itemId(店铺用 url)精准定位,而非依赖完整 title 匹配。

## 3. 关键决策(brainstorming 已确认)

| 维度 | 决策 |
|---|---|
| 轨迹数据模型 | **每商品一份状态快照**(选中那一刻的面板状态) |
| 范围 | **商品 + 店铺一起改造**(店铺无 itemId,用 title/url 双校验) |
| UI 可见性 | **不展示轨迹**(用户无感,纯隐式记录) |
| 失败处理 | **任一商品找不到即中断整个视频发布** |
| 加载更多 | **上限内找到就停**(默认 5 次) |
| 持久化 | 仅写入 `drafts.draft_data` JSON,不新增表/字段 |
| 后端代码组织 | **抽公共 helper 模块** `_link_ops.py`,picker.py 和 platform.py 共用 |

## 4. 架构与文件改动

```
backend/impl/taobao_guanghe/
├── _link_ops.py            【新】帧级工具函数(纯函数,参数为 frame)
├── picker.py               【改】内部搜索/筛选/抓取调用切到 _link_ops
└── platform.py             【改】_link_products_or_shops 重写为「分组重现 + itemId 定位」

backend/
├── app.py                  【改】4 处 publish 路由透传字段名:
│                                guangheProductNames → guangheProducts(完整对象)
│                                guangheShopNames   → guangheShops(完整对象)
│                              (读取时兼容旧字段名,降级为旧路径)
└── ext_api/__init__.py     【无改】drafts 表的 draft_data JSON 字段天然支持

frontend/src/
├── components/GuangheItemPicker.vue   【改】selectedNames → selectedItems
│       每次 onCardClick 时打包当前面板状态为 trace 快照
├── api/taobaoGuanghe.js               【无改】
└── views/PublishCenter.vue            【改】
       - form.guangheProducts / guangheShops 由 [{title,image}] 升级为 [{title,image,id,trace}]
       - 提交字段 guangheProductNames → guangheProducts / guangheShopNames → guangheShops
       - saveDraft/loadDraft 自动随 draft_data JSON 持久化(无需特殊处理)
```

## 5. 数据结构(trace schema)

### 5.1 前端 form 字段(持久化到 drafts.draft_data JSON)

```js
// form.guangheProducts / form.guangheShops
[
  {
    title: "小米17 Pro 16GB+512GB...",  // 显示用
    image: "https://...",               // 显示用
    id: "674528301234",                 // 商品 itemId / 店铺用 title 兜底
    trace: {
      tab: "preferred",                 // 'bought' | 'preferred' | 'shop'
      keyword: "小米17",                // 搜索词,空串=未搜索
      rule: "主推品",                   // 推荐规则,空串=默认;店铺固定空串
      category: "全部"                  // 品类,空串=默认;店铺固定空串
    }
  },
  // ...
]
```

### 5.2 字段说明

| 字段 | 类型 | 商品模式 | 店铺模式 |
|---|---|---|---|
| `tab` | string | `bought` / `preferred` | 固定 `shop` |
| `keyword` | string | 搜索框内容 | 搜索框内容 |
| `rule` | string | 推荐规则文本(从 DOM 抓) | 固定空串 |
| `category` | string | 品类文本 | 固定空串 |

**`id` 字段语义**:
- 商品模式: 淘宝 `itemId`(数字字符串,从 `a[href*="item.taobao.com/item.htm?id=xxx"]` 提取)
- 店铺模式: picker 抓取时返回 `id = title || url`(回退到 url,见 `picker.py:_scrape_shops`),发布时双校验(先 title 文本匹配,若疑似重复再校验 url 包含)

**不记录** `loadMore` 次数 —— 发布时「上限 5 次内找到 itemId 就停」。

### 5.3 Trace 签名(用于发布时分组)

```python
def trace_signature(trace: dict) -> tuple:
    return (trace["tab"], trace["keyword"], trace["rule"], trace["category"])
```

签名相同的商品归为一一组,组内一次性「恢复状态 → 上限内翻页 → 勾选所有 itemId」。

### 5.4 兼容性

- **前端读取旧 drafts**:`trace`/`id` 缺失仍能正常显示(title+image 回显),发布前不阻断(让后端走旧路径)
- **后端读取旧数据**:`trace` 缺失或 `id` 缺失时退回旧路径(title 搜+span[title] 匹配);找不到按"中断发布"处理
- **极旧数据**(`guangheProductNames` 是字符串数组):后端在 app.py 兼容字段名,读取后包成 `{title: name}` 走旧路径

## 6. 数据流

### 6.1 阶段 A · 用户选品(前端)

```
用户操作                           前端 trace 字段
─────────────────────────────────────────────────
打开 picker                         activeRule/categories 初始化(picker/open)
点 tab 切换                         activeTab 变更
点「推荐规则」                       activeRule 变更
点「品类」                           activeCategory 变更
点搜索按钮                           searchKeyword 变更
点加载更多                          (不记录)
─────────────────────────────────────────────────
点商品卡片选中                       
  ↓ 快照当前面板状态
  selectedItems.push({
    title, image, id,
    trace: {
      tab: activeTab,
      keyword: searchKeyword,
      rule: activeRule,
      category: activeCategory,
    }
  })
```

trace 在卡片选中那一刻快照,后续面板状态变化不影响已选商品的 trace。

### 6.2 阶段 B · 提交发布

```
PublishCenter.guangheProducts (每项含 id + trace)
  ↓ POST /api/publish (或 /api/v2/drafts/batch-publish)
app.py 完整透传给 platform.publish_video
  ↓
platform._upload_single_video(link_items=[{title,id,trace}, ...])
  ↓
platform._link_products_or_shops(frame, link_type, items)
```

### 6.3 阶段 C · 后端按轨迹重现

```
按 trace_signature 分组:
  组1: trace={tab:preferred, kw:'小米17', rule:'主推品', cat:'全部'}, items=[id=123, id=124]
  组2: trace={tab:preferred, kw:'手机壳',  rule:'',       cat:''},     items=[id=125]

对每组:
  1. _link_ops.reset_panel(frame, type)         # 切到对应 radio
  2. _link_ops.open_picker(frame, type)         # 点「添加商品/店铺」卡片
  3. 切到 trace.tab 对应的 tab(店铺模式跳过)
  4. if trace.rule:     _link_ops.click_filter(frame, '推荐规则', trace.rule)
  5. if trace.category: _link_ops.click_filter(frame, '品类筛选', trace.category)
  6. if trace.keyword:  _link_ops.search(frame, trace.keyword)
  7. 循环最多 5 次:
       items_now = _link_ops.scrape(frame)
       对每个组内仍待找的 id:
         若出现在 items_now 里:
           - disabled=true  → raise RuntimeError(中断,不允许跳过)
           - 已勾选          → 标记完成
           - 未勾选          → 勾选,标记完成
       组内全部完成 → break
       仍有未命中且有「加载更多」 → 点加载更多,继续循环
       否则 → break
  8. 仍有未命中 → raise RuntimeError("未找到的商品 id: <列表>")  ← 中断
  9. 点「确定」关闭面板,准备下一组
```

## 7. 错误处理

| 失败点 | 检测 | 处理 |
|---|---|---|
| 旧数据无 `id`/`trace` | `if not item.get("trace")` | 退回旧路径(title 搜 + span[title] 匹配) |
| `guangheProducts` 是字符串数组 | `isinstance(item, str)` | 包成 `{title: item}` 走旧路径 |
| 5 次加载更多后仍有 itemId 未命中 | 计数器 + 剩余集合比对 | `raise RuntimeError` 中断 |
| 找到的商品 disabled | 抓取阶段 `disabled: true` | 中断,错误信息标注「商品不可选」 |
| 搜索后列表空 | `_scrape` 返回 `items=[]` | 立即中断,不空等 |
| 切 tab/筛选点击无反应 | 切完后校验 active 状态,重试 1 次 | 仍失败中断 |
| 浏览器/网络异常 | 异常冒泡 | 现有 except 捕获,记日志+截屏 |

所有中断通过 `raise RuntimeError` 冒泡到 `_upload_single_video` 之外,由 app.py 现有错误处理统一捕获并发到 status_queue。

## 8. 测试策略

### 8.1 后端单元测试

| 测试文件 | 测什么 |
|---|---|
| `test_guanghe_trace_signature.py` | `trace_signature` 分组正确性 |
| `test_guanghe_link_ops_locate.py` | `_link_ops.locate_and_check`:mock frame.evaluate,验证 itemId 匹配+disabled 检测+已选检测+点击 |
| `test_guanghe_link_group_replay.py` | 端到端:mock _link_ops 所有方法,验证分组循环、5 次上限、找不到时 raise |

不测:DOM 选择器具体写法(改用人工冒烟+截图验收)。

### 8.2 前端组件测试(如已配置 vitest)

| 测试 | 测什么 |
|---|---|
| `GuangheItemPicker.trace.test.js` | 多次"搜→选"后,selectedItems 每项 trace 是当时快照而非最新状态 |
| `GuangheItemPicker.legacy.test.js` | `initSelected` 收到旧格式 `[{title,image}]` 时正常回显,trace 缺失不报错 |

### 8.3 手动冒烟(验收清单)

```
1. 选品轨迹验证
   ① 搜「小米17」→ 选商品 A
   ② 不动筛选,继续选商品 B
   ③ 清空搜索 → 选商品 C
   → 确认 → network 面板查 POST /api/publish payload:
     guangheProducts[0].trace.keyword == '小米17'
     guangheProducts[1].trace.keyword == '小米17'  (A、B 共享)
     guangheProducts[2].trace.keyword == ''

2. 发布可靠性
   → 后端日志:三组分组、按需加载更多、勾选成功
   → 截图 logs/guanghe_before_submit.png 面板里 3 个商品都勾上

3. 故意改坏 trace.keyword 为搜不到的词 → 验证中断 + 错误提示

4. 草稿保存 → 刷新 → 加载草稿 → guangheProducts 完整恢复(含 trace)

5. 店铺模式重复 1-4 步
```

## 9. 实施顺序

```
Step 1 — 后端 helper + 单元测试(可独立 PR,无破坏性)
  ├─ 新建 backend/impl/taobao_guanghe/_link_ops.py
  ├─ picker.py 内部调用切换到 _link_ops
  └─ 新增 3 个测试文件

Step 2 — 后端 platform.py 重写 _link_products_or_shops(依赖 Step 1)
  ├─ 改字段读取:guangheProducts/guangheShops(完整对象)
  ├─ app.py 4 处路由字段名同步改(读时兼容旧名)
  └─ publish_video 参数读取更新

Step 3 — 前端 picker trace 快照(可独立 PR,与 Step 2 通过兼容字段对接)
  ├─ GuangheItemPicker:activeTab/activeRule/activeCategory/searchKeyword 状态
  ├─ onCardClick 时快照 trace
  ├─ onConfirm emit 完整对象数组
  └─ 兼容旧 initSelected

Step 4 — 前端 PublishCenter 字段升级(依赖 Step 3)
  ├─ form.guangheProducts 存完整对象
  ├─ saveDraft/loadDraft 随 draft_data JSON 自动持久化
  └─ 提交 publish 改传完整对象数组

Step 5 — 联调验收(手动跑 8.3 的冒烟清单)
```

Step 1、3 可并行;Step 2、4 依赖前面;每个 Step 内 commit 自洽。

## 10. 验收标准

| 维度 | 通过线 |
|---|---|
| 单测 | `pytest backend/tests/test_guanghe_*.py` 全过 |
| 兼容 | 加载旧格式 `[{title,image}]` 草稿不报错;旧草稿发布用旧路径尝试,失败时中断 |
| 选品 UX | 多次"搜→筛→选"轨迹被正确快照(network 面板验) |
| 发布可靠性 | 三商品共享轨迹的场景,日志显示「组内 1 次搜索 + 必要加载更多 + 勾选多个」 |
| 中断 | 故意改坏 trace 能稳定中断,错误信息能定位到具体 itemId |
| 店铺 | 重复一遍,行为对齐 |
