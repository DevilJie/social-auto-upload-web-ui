# 京东视频发布 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现京东平台(`platform_id = 20`)视频发布全流程:视频上传、封面、标题、关联挂件(商品/小说)、创作声明、定时发布、发布按钮。

**Architecture:** 完全沿用淘宝光合 picker 架构。后端分三层:`_jd_link_ops.py`(纯函数 DOM 操作库)→ `picker.py`(`JdPickerSession` + `_SessionPool`)→ `platform.py`(`JdPlatform` 继承 `BasePlatform`)。前端仿 `GuangheItemPicker.vue` 写 `JdItemPicker.vue`。trace 模型简化为 `{keyword, page}`(无 tab/rule/category)。发布时按 trace 分组重现(搜索 → 翻页 → 按 id 精准勾选),关联小说用下拉搜索组件(不开 picker)。

**Tech Stack:** Python 3 / Flask / Playwright(async) / Vue 3 / Element Plus / SQLite

**Spec:** [docs/superpowers/specs/2026-08-13-jingdong-publish-design.md](../specs/2026-08-13-jingdong-publish-design.md)

**约定:**
- 不写自动化测试(用户自行测试)
- 所有 commit 使用中文 message
- 浏览器策略: 发布 `headless=False`,picker `headless=True`
- 发布收尾必须用 `close_browser(self.browser, is_close_by_code=True)`

---

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `backend/impl/jd/__init__.py` | jd 模块标记 | 新建(空) |
| `backend/impl/jd/_jd_link_ops.py` | 帧级 DOM 工具函数(纯函数) | 新建(~350 行) |
| `backend/impl/jd/picker.py` | JdPickerSession + _SessionPool | 新建(~300 行) |
| `backend/impl/jd/platform.py` | JdPlatform 实现 | 新建(~600 行) |
| `backend/blueprints/jd_bp.py` | picker 路由蓝图 | 新建(~200 行) |
| `backend/impl/registry.py` | 注册 platform_id 20 | 改 |
| `backend/app.py` | 注册 jd_bp + 4 处 publish 路由透传 jd 字段 | 改 |
| `backend/ext_api/__init__.py` | _PLATFORM_ID_MAP / platform_map / type_to_platform 添加 jd | 改 |
| `frontend/src/api/jd.js` | picker API 客户端 | 新建(~45 行) |
| `frontend/src/assets/logos/jd.png` | 京东 logo | 新建 |
| `frontend/src/components/JdItemPicker.vue` | 京东选品弹窗 | 新建(~550 行) |
| `frontend/src/config/platforms.js` | 添加 JD 配置 + logo import | 改 |
| `frontend/src/views/PublishCenter.vue` | 京东专属卡片 + 引入 JdItemPicker | 改 |

---

## Phase 1: 后端基础 — `_jd_link_ops.py` + `picker.py` + `jd_bp.py`

### Task 1: 创建 jd 模块骨架

**Files:**
- Create: `backend/impl/jd/__init__.py`

- [ ] **Step 1.1: 创建 jd 模块目录与空 __init__.py**

Create `backend/impl/jd/__init__.py`:

```python
"""京东平台实现(jingdong publishing center at https://dr.jd.com/jm/)."""
```

- [ ] **Step 1.2: 验证模块可被导入**

Run:
```bash
cd backend && python -c "from impl.jd import _jd_link_ops; print('ok')"
```

Expected: `ModuleNotFoundError: No module named 'impl.jd._jd_link_ops'`(预期,因为文件还不存在)

- [ ] **Step 1.3: 提交**

```bash
git add backend/impl/jd/__init__.py
git commit -m "feat(jd): 创建京东平台模块骨架"
```

---

### Task 2: 实现 `_jd_link_ops.py` — trace_signature + 抓取

**Files:**
- Create: `backend/impl/jd/_jd_link_ops.py`

- [ ] **Step 2.1: 创建 _jd_link_ops.py 骨架 + trace_signature**

Create `backend/impl/jd/_jd_link_ops.py`:

```python
"""京东关联商品 picker — 帧级纯函数 DOM 操作库。

所有函数以 frame 为参数(京东发布页无跨域 iframe,frame 即 page)。
模块是 picker.py 与 platform.py 共享的 DOM 操作代码。

DOM 锚点参考(2026-08 京东发布页):
- 商品卡片:    ._sku-card-mygoods-con_jvzh5_77
- 商品图:      ._sku-card-img_jvzh5_154
- 商品名:      ._sku-name_jvzh5_204
- 商品价格:    ._price-value_jvzh5_277
- 店铺名:      ._shop-name_jvzh5_295
- 勾选框:      ._sku-card-checkbox-area_jvzh5_103 内 .jd-checkbox-wrapper
- 抽屉底部:    ._custom-footer-btns_38ot8_105 内 [data-spm-click='...SelectionAdd']
- 搜索框:      .search-input-content-input 或 .jd-input-affix-wrapper input
- 分页:        .jd-pagination-item / .jd-pagination-prev / .jd-pagination-next
"""

from collections import defaultdict
from dataclasses import dataclass, field


# ---------- trace 签名 ----------

def trace_signature(trace: dict) -> tuple[str, int]:
    """trace 签名:(keyword, page)。"""
    return (trace.get("keyword", ""), trace.get("page", 1))


# ---------- 数据类 ----------

@dataclass
class LocateResult:
    """locate_and_check 返回值。"""
    checked: list[str] = field(default_factory=list)
    already: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


# ---------- 等待工具 ----------

async def wait_for_selector(frame, selector: str, timeout: float = 10):
    """等待 selector 出现,内部用 Playwright frame.wait_for_selector。"""
    await frame.wait_for_selector(selector, timeout=timeout * 1000, state="visible")


async def sleep(seconds: float):
    import asyncio
    await asyncio.sleep(seconds)


# ---------- 商品抓取 ----------

async def scrape_products(frame) -> list[dict]:
    """抓当前激活面板的商品列表 -> [{title, image, id, price, shop_name}, ...]。

    商品 id 提取优先级:
    1. ._sku-card-desc_jvzh5_94 上的 data-spm-click 属性(如 'publishVideoMySkuCardSelect')
       之外,通常需要从 data 属性或图片 URL 提取 skuId
    2. 从图片 URL 提取:    //m.360buyimg.com/.../{skuId}.png
    3. 兜底: 用 .jd-checkbox-input 的 value 或 dataset
    """
    items = []
    cards = await frame.query_selector_all("._sku-card-mygoods-con_jvzh5_77")
    for card in cards:
        title_el = await card.query_selector("._sku-name_jvzh5_204")
        img_el = await card.query_selector("._sku-card-img_jvzh5_154")
        price_el = await card.query_selector("._price-value_jvzh5_277")
        shop_el = await card.query_selector("._shop-name_jvzh5_295")
        checkbox_el = await card.query_selector(".jd-checkbox-input")

        title = (await title_el.inner_text()).strip() if title_el else ""
        image = await img_el.get_attribute("src") if img_el else ""
        price = (await price_el.inner_text()).strip() if price_el else ""
        shop_name = (await shop_el.inner_text()).strip() if shop_el else ""

        # 商品 id 提取:从图片 URL 中提取 skuId
        # URL 形式: //m.360buyimg.com/ceco/jfs/t1/501561/2/2768/2282669/6a79e043F78f1e83e/{skuId}.png
        sku_id = ""
        if image:
            parts = image.rstrip(".png").split("/")
            if parts:
                sku_id = parts[-1]
        # 兜底:从 checkbox 的 data 属性
        if not sku_id and checkbox_el:
            sku_id = await checkbox_el.get_attribute("value") or ""
            if not sku_id:
                sku_id = await checkbox_el.get_attribute("data-sku-id") or ""

        items.append({
            "title": title,
            "image": image,
            "id": sku_id,
            "price": price,
            "shop_name": shop_name,
        })
    return items
```

- [ ] **Step 2.2: 验证导入与函数签名**

Run:
```bash
cd backend && python -c "
from impl.jd._jd_link_ops import trace_signature, scrape_products, LocateResult
t = {'keyword': '小米', 'page': 2}
print(trace_signature(t))
r = LocateResult()
print(r.checked, r.missing)
"
```

Expected: `('小米', 2)` followed by `([], [])`

- [ ] **Step 2.3: 提交**

```bash
git add backend/impl/jd/_jd_link_ops.py
git commit -m "feat(jd): _jd_link_ops.py 骨架 + trace_signature + scrape_products"
```

---

### Task 3: 实现 `_jd_link_ops.py` — 抽屉与 radio 操作

**Files:**
- Modify: `backend/impl/jd/_jd_link_ops.py`

- [ ] **Step 3.1: 追加 switch_radio / click_add_card / wait_panel_ready**

Append to `backend/impl/jd/_jd_link_ops.py`:

```python
# ---------- 抽屉与 radio ----------

async def switch_radio(frame, type_: str):
    """切商品/小说 radio:type_='product' 或 'novel'。

    DOM 锚点:
    - 商品 radio: .jd-radio-wrapper input[value='1']
    - 小说 radio: .jd-radio-wrapper input[value='3']
    """
    value = "1" if type_ == "product" else "3"
    label_selector = f".jd-radio-wrapper:has(input.jd-radio-input[value='{value}'])"
    label = await frame.wait_for_selector(label_selector, timeout=10_000)
    await label.click()


async def click_add_card(frame):
    """点 '添加商品' 卡片,打开关联商品抽屉。

    DOM 锚点: .addgoods-upload[data-spm-click='publishGoodsAddGood']
    """
    card = await frame.wait_for_selector(
        ".addgoods-upload[data-spm-click='publishGoodsAddGood']",
        timeout=10_000,
    )
    await card.click()


async def wait_panel_ready(frame, timeout: float = 15):
    """等抽屉 .jd-drawer-wrapper-body 出现且包含商品卡片。

    等待策略:
    1. 等 .jd-drawer-wrapper-body 可见
    2. 等至少 1 个商品卡片 ._sku-card-mygoods-con_jvzh5_77 出现
    """
    await frame.wait_for_selector(
        ".jd-drawer-wrapper-body",
        timeout=timeout * 1000,
        state="visible",
    )
    await frame.wait_for_selector(
        "._sku-card-mygoods-con_jvzh5_77",
        timeout=timeout * 1000,
        state="visible",
    )
    # 给一次额外渲染时间
    await sleep(0.5)
```

- [ ] **Step 3.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd._jd_link_ops import switch_radio, click_add_card, wait_panel_ready; print('ok')"
```

Expected: `ok`

- [ ] **Step 3.3: 提交**

```bash
git add backend/impl/jd/_jd_link_ops.py
git commit -m "feat(jd): _jd_link_ops.py 抽屉与 radio 操作"
```

---

### Task 4: 实现 `_jd_link_ops.py` — 搜索与分页

**Files:**
- Modify: `backend/impl/jd/_jd_link_ops.py`

- [ ] **Step 4.1: 追加 clear_search / search / 分页函数**

Append to `backend/impl/jd/_jd_link_ops.py`:

```python
# ---------- 搜索 ----------

async def clear_search(frame):
    """清空搜索框(京东本店商品搜索)。

    DOM 锚点: ._my-goods-container-head_aejm5_69 内的 .jd-input
              或  .search-input-content-input(站内搜索 tab)
    通过 triple_click + Delete 确保清空干净。
    """
    # 优先匹配本店商品 tab 的搜索框
    inp = await frame.query_selector(
        "._my-goods-container-head_aejm5_69 .jd-input"
    )
    if not inp:
        inp = await frame.query_selector(".search-input-content-input")
    if not inp:
        inp = await frame.query_selector(".jd-drawer-wrapper-body .jd-input")
    if inp:
        await inp.click(click_count=3)  # triple_click 选中
        await frame.keyboard.press("Delete")
        await inp.fill("")
        await sleep(0.3)


async def search(frame, keyword: str):
    """输入搜索关键词并回车触发搜索。

    实现细节:
    - click + fill(避免 React 监听丢失)
    - fill 后必须 press Enter(京东搜索框需回车触发)
    - 等 ._sku-card-mygoods-con_jvzh5_77 重新渲染
    """
    inp = await frame.query_selector(
        "._my-goods-container-head_aejm5_69 .jd-input"
    )
    if not inp:
        inp = await frame.query_selector(".search-input-content-input")
    if not inp:
        inp = await frame.query_selector(".jd-drawer-wrapper-body .jd-input")
    if not inp:
        raise RuntimeError("未找到搜索框")

    await inp.click()
    await inp.fill(keyword)
    await sleep(0.3)
    await frame.keyboard.press("Enter")

    # 等搜索结果(loading 消失 + 至少一张卡片)
    await frame.wait_for_selector(
        "._sku-card-mygoods-con_jvzh5_77",
        timeout=10_000,
        state="visible",
    )
    await sleep(0.5)


async def wait_search_results(frame, timeout: float = 10):
    """等搜索结果稳定(loading 消失 + 至少一张卡片)。

    若 0 条结果,可能等不到卡片,需要 catch 异常并允许 0 结果继续。
    """
    try:
        await frame.wait_for_selector(
            "._sku-card-mygoods-con_jvzh5_77",
            timeout=timeout * 1000,
            state="visible",
        )
    except Exception:
        pass  # 允许 0 结果
    await sleep(0.5)


# ---------- 分页 ----------

async def get_current_page(frame) -> int:
    """从 .jd-pagination-item-active 读取当前页码(返回数字)。"""
    el = await frame.query_selector(".jd-pagination-item-active")
    if not el:
        return 1
    txt = (await el.inner_text()).strip()
    try:
        return int(txt)
    except ValueError:
        return 1


async def get_total_pages(frame) -> int:
    """从 .jd-pagination 最后一个数字页码项读取总页数。"""
    items = await frame.query_selector_all(".jd-pagination-item.jd-pagination-item-1, .jd-pagination-item:not(.jd-pagination-item-active)")
    if not items:
        # 退而求其次:只找数字页
        items = await frame.query_selector_all(".jd-pagination-item")
    max_page = 1
    for item in items:
        txt = (await item.inner_text()).strip()
        try:
            n = int(txt)
            if n > max_page:
                max_page = n
        except ValueError:
            continue
    return max_page


async def go_page(frame, page: int):
    """点击指定页码按钮(数字按钮或上下页)。

    策略:
    - page == 1: 不操作
    - page > current: 多次点 .jd-pagination-next
    - page < current: 多次点 .jd-pagination-prev
    - 其他: 点 .jd-pagination-item-{page}
    """
    current = await get_current_page(frame)
    if page == current:
        return

    if page > current:
        # 用 next 按钮直到翻到目标页
        for _ in range(page - current):
            nxt = await frame.query_selector(".jd-pagination-next:not(.jd-pagination-disabled)")
            if not nxt:
                raise RuntimeError(f"无法翻到第 {page} 页:next 按钮不可用")
            await nxt.click()
            await wait_page_change(frame)
    else:
        # 用 prev 按钮直到翻到目标页
        for _ in range(current - page):
            prv = await frame.query_selector(".jd-pagination-prev:not(.jd-pagination-disabled)")
            if not prv:
                raise RuntimeError(f"无法翻到第 {page} 页:prev 按钮不可用")
            await prv.click()
            await wait_page_change(frame)


async def wait_page_change(frame, timeout: float = 10):
    """等分页切换完成(页码变化 + 至少一张卡片重新渲染)。

    检测方法:比较当前 active 页码与触发前的不同 → 至少一张卡片可见
    """
    await sleep(0.5)  # 简单等待,后续可改为条件等待
    try:
        await frame.wait_for_selector(
            "._sku-card-mygoods-con_jvzh5_77",
            timeout=timeout * 1000,
            state="visible",
        )
    except Exception:
        pass
```

- [ ] **Step 4.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd._jd_link_ops import clear_search, search, get_current_page, go_page; print('ok')"
```

Expected: `ok`

- [ ] **Step 4.3: 提交**

```bash
git add backend/impl/jd/_jd_link_ops.py
git commit -m "feat(jd): _jd_link_ops.py 搜索与分页"
```

---

### Task 5: 实现 `_jd_link_ops.py` — 勾选与关闭

**Files:**
- Modify: `backend/impl/jd/_jd_link_ops.py`

- [ ] **Step 5.1: 追加 locate_and_check / click_confirm / close_panel**

Append to `backend/impl/jd/_jd_link_ops.py`:

```python
# ---------- 勾选 ----------

async def locate_and_check(frame, target_ids: list[str]) -> LocateResult:
    """按 id 精准勾选目标商品,返回 4 桶结果。

    流程:
    1. 抓当前页所有商品(含 id)
    2. 对每个 target_id:
       - 不在当前页 → missing
       - 在但 checkbox disabled → disabled
       - 在但已勾选 → already
       - 在且未勾选 → click checkbox 勾选,加入 checked

    返回 LocateResult {checked, already, disabled, missing}
    """
    result = LocateResult()
    target_set = set(target_ids)

    cards = await frame.query_selector_all("._sku-card-mygoods-con_jvzh5_77")
    page_ids = []
    for card in cards:
        title_el = await card.query_selector("._sku-name_jvzh5_204")
        img_el = await card.query_selector("._sku-card-img_jvzh5_154")
        checkbox_el = await card.query_selector(".jd-checkbox-input")

        title = (await title_el.inner_text()).strip() if title_el else ""
        image = await img_el.get_attribute("src") if img_el else ""

        # 提取商品 id(同 scrape_products)
        sku_id = ""
        if image:
            parts = image.rstrip(".png").split("/")
            if parts:
                sku_id = parts[-1]
        if not sku_id and checkbox_el:
            sku_id = await checkbox_el.get_attribute("value") or ""

        # 检查是否已勾选
        is_checked = False
        if checkbox_el:
            checked_attr = await checkbox_el.get_attribute("checked")
            is_checked = checked_attr is not None

        # 检查是否 disabled
        is_disabled = False
        if checkbox_el:
            disabled_attr = await checkbox_el.get_attribute("disabled")
            is_disabled = disabled_attr is not None

        page_ids.append((sku_id, card, checkbox_el, is_checked, is_disabled))

    # 桶分类
    found_ids = {pid for pid, *_ in page_ids}
    for tid in target_ids:
        if tid not in found_ids:
            result.missing.append(tid)

    for pid, card, checkbox_el, is_checked, is_disabled in page_ids:
        if pid not in target_set:
            continue
        if is_disabled:
            result.disabled.append(pid)
            continue
        if is_checked:
            result.already.append(pid)
            continue
        # 勾选
        try:
            if checkbox_el:
                await checkbox_el.click()
                result.checked.append(pid)
            else:
                # 退而求其次:点整张卡片
                await card.click()
                result.checked.append(pid)
        except Exception:
            result.missing.append(pid)

    return result


# ---------- 关闭 ----------

async def click_confirm(frame):
    """点抽屉底部'确定'按钮,关闭抽屉并提交已选商品。

    DOM 锚点:
    ._custom-footer-btns_38ot8_105 内的 [data-spm-click='publishVideoNewGoodsSelectionAdd']
    """
    btn = await frame.wait_for_selector(
        "[data-spm-click='publishVideoNewGoodsSelectionAdd']",
        timeout=10_000,
    )
    await btn.click()
    # 等抽屉关闭
    await frame.wait_for_selector(
        ".jd-drawer-wrapper-body",
        timeout=5_000,
        state="hidden",
    )


async def close_panel(frame):
    """按 Esc 或点 .jd-drawer-close 关闭抽屉。"""
    try:
        close_btn = await frame.query_selector(".jd-drawer-close")
        if close_btn:
            await close_btn.click()
        else:
            await frame.keyboard.press("Escape")
        await sleep(0.5)
    except Exception:
        pass
```

- [ ] **Step 5.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd._jd_link_ops import locate_and_check, click_confirm, close_panel; print('ok')"
```

Expected: `ok`

- [ ] **Step 5.3: 提交**

```bash
git add backend/impl/jd/_jd_link_ops.py
git commit -m "feat(jd): _jd_link_ops.py 勾选与关闭"
```

---

### Task 6: 实现 `_jd_link_ops.py` — 小说下拉

**Files:**
- Modify: `backend/impl/jd/_jd_link_ops.py`

- [ ] **Step 6.1: 追加 select_novel 与 wait_novel_dropdown**

Append to `backend/impl/jd/_jd_link_ops.py`:

```python
# ---------- 小说下拉 ----------

async def wait_novel_dropdown(frame, timeout: float = 10):
    """等小说下拉框出现(rc-virtual-list-holder-inner)。"""
    await frame.wait_for_selector(
        ".rc-virtual-list-holder-inner",
        timeout=timeout * 1000,
        state="visible",
    )


async def select_novel(frame, novel_title: str):
    """在小说下拉中按 title 文本选择。

    步骤:
    1. 点击小说 .jd-select(jd-select-show-search)
    2. 在搜索 input 内 type 关键词
    3. 等下拉出现 .rc-virtual-list-holder-inner
    4. 找含 novel_title 的 .jd-select-item-option
    5. click 选中

    DOM 锚点:
    - 小说 select: .content-declaration-wrapper 之外的第二个 .jd-select-show-search
      或关联挂件 radio 选 novel 后出现的 .jd-select(.related-novel-wrapper)
    - 下拉项:    .jd-select-item-option .related-book-item-right-name
    """
    # 1. 找到小说 select 并点击
    # 京东关联挂件 radio 切到 novel 后会出现一个 .jd-select-show-search
    select = await frame.wait_for_selector(
        ".jd-select-show-search",
        timeout=10_000,
    )
    await select.click()
    await sleep(0.5)

    # 2. 找到搜索 input 并 type
    search_input = await frame.wait_for_selector(
        ".jd-select-selection-search-input",
        timeout=10_000,
    )
    await search_input.click()
    # 用 press_sequentially 逐字输入(React 富文本友好,见 CLAUDE.md §6)
    await search_input.press_sequentially(novel_title, delay=100)
    await sleep(1.0)  # 等搜索完成

    # 3. 等下拉出现
    await wait_novel_dropdown(frame)
    await sleep(0.5)

    # 4. 找含目标 title 的下拉项
    items = await frame.query_selector_all(".jd-select-item-option")
    if not items:
        raise RuntimeError(f"小说搜索无结果: {novel_title}")

    target_item = None
    for item in items:
        name_el = await item.query_selector(".related-book-item-right-name")
        if name_el:
            name_txt = (await name_el.inner_text()).strip()
            if name_txt == novel_title:
                target_item = item
                break

    if not target_item:
        # 模糊匹配:包含关键词
        for item in items:
            name_el = await item.query_selector(".related-book-item-right-name")
            if name_el:
                name_txt = (await name_el.inner_text()).strip()
                if novel_title in name_txt:
                    target_item = item
                    break

    if not target_item:
        raise RuntimeError(f"小说未找到: {novel_title}")

    # 5. click 选中
    await target_item.click()
    await sleep(0.5)
```

- [ ] **Step 6.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd._jd_link_ops import select_novel, wait_novel_dropdown; print('ok')"
```

Expected: `ok`

- [ ] **Step 6.3: 提交**

```bash
git add backend/impl/jd/_jd_link_ops.py
git commit -m "feat(jd): _jd_link_ops.py 小说下拉"
```

---

### Task 7: 实现 `picker.py` — JdPickerSession

**Files:**
- Create: `backend/impl/jd/picker.py`

- [ ] **Step 7.1: 创建 picker.py + JdPickerSession**

Create `backend/impl/jd/picker.py`:

```python
"""京东关联商品 picker session — 后台 headless browser。

按 account_id 单例复用:
- 同账号同时只能开一个 picker(避免资源竞争)
- picker 与 platform 共享 _jd_link_ops(同一份 DOM 操作)

浏览器策略:headless=True(参考淘宝光合 picker ad3b8d8 改动)
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from backend.impl._browser import create_browser, close_browser
from backend.impl.jd import _jd_link_ops as link_ops
from backend.conf import get_cookie_file_path

logger = logging.getLogger(__name__)


class JdPickerSession:
    """单账号单 headless browser session。"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.browser = None
        self.page = None

    async def open(self) -> list[dict]:
        """启动浏览器进入选择面板,返回首屏商品列表。"""
        if self.browser is not None:
            raise RuntimeError(f"picker session 已存在: {self.account_id}")

        cookie_file = get_cookie_file_path(self.account_id, "jd")
        storage_state = str(cookie_file) if cookie_file.exists() else None

        # 后台 headless(与淘宝光合 picker ad3b8d8 一致)
        self.browser = await create_browser(headless=True)
        if storage_state:
            from backend.impl._browser import create_context
            ctx = await create_context(self.browser, storage_state=storage_state)
            self.page = await ctx.new_page()
        else:
            ctx = await self.browser.new_context()
            self.page = await ctx.new_page()

        # goto 发布页
        await self.page.goto(
            "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop",
            wait_until="domcontentloaded",
        )
        # 等 SPA 路由 + 发布表单渲染
        await asyncio.sleep(2)
        await self.page.wait_for_selector(
            ".video-upload-wrapper",
            timeout=15_000,
            state="visible",
        )

        # 切商品 radio(默认已是商品,但保险起见)
        await link_ops.switch_radio(self.page, "product")
        await link_ops.click_add_card(self.page)
        await link_ops.wait_panel_ready(self.page)

        # 返回首屏商品
        return await link_ops.scrape_products(self.page)

    async def search(self, keyword: str) -> list[dict]:
        """搜索并返回商品列表。"""
        if self.page is None:
            raise RuntimeError("picker 未打开,请先调用 open()")
        await link_ops.clear_search(self.page)
        if keyword:
            await link_ops.search(self.page, keyword)
            await link_ops.wait_search_results(self.page)
        return await link_ops.scrape_products(self.page)

    async def go_page(self, page: int) -> list[dict]:
        """翻页并返回商品列表。"""
        if self.page is None:
            raise RuntimeError("picker 未打开")
        await link_ops.go_page(self.page, page)
        return await link_ops.scrape_products(self.page)

    async def close(self):
        """释放浏览器资源(必须在 finally 中调用)。"""
        try:
            if self.browser is not None:
                await close_browser(self.browser, is_close_by_code=True)
        except Exception as e:
            logger.warning(f"关闭 picker 浏览器失败: {e}")
        finally:
            self.browser = None
            self.page = None
```

- [ ] **Step 7.2: 验证 import**

Run:
```bash
cd backend && python -c "from impl.jd.picker import JdPickerSession; s = JdPickerSession('test'); print(s.account_id)"
```

Expected: `test`

- [ ] **Step 7.3: 提交**

```bash
git add backend/impl/jd/picker.py
git commit -m "feat(jd): picker.py JdPickerSession 实现"
```

---

### Task 8: 实现 `picker.py` — _SessionPool

**Files:**
- Modify: `backend/impl/jd/picker.py`

- [ ] **Step 8.1: 追加 _SessionPool + pool 单例**

Append to `backend/impl/jd/picker.py`:

```python
# ---------- session 池 ----------


class _SessionPool:
    """按 account_id 管理 picker session,同账号同时只能开一个。"""

    def __init__(self):
        self._sessions: dict[str, JdPickerSession] = {}

    def get_or_create(self, account_id: str) -> JdPickerSession:
        existing = self._sessions.get(account_id)
        if existing is not None:
            return existing
        new_session = JdPickerSession(account_id)
        self._sessions[account_id] = new_session
        return new_session

    def get(self, account_id: str) -> Optional[JdPickerSession]:
        return self._sessions.get(account_id)

    def release(self, account_id: str):
        """释放 session 并关闭浏览器。"""
        session = self._sessions.pop(account_id, None)
        if session is not None:
            # 异步关闭:跨线程调用
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(session.close())
                else:
                    loop.run_until_complete(session.close())
            except RuntimeError:
                # 没有运行中的 loop,直接同步关闭
                pass

    def has(self, account_id: str) -> bool:
        return account_id in self._sessions


pool = _SessionPool()
```

- [ ] **Step 8.2: 验证 import**

Run:
```bash
cd backend && python -c "
from impl.jd.picker import pool, JdPickerSession
s1 = pool.get_or_create('acc1')
s2 = pool.get_or_create('acc1')
print(s1 is s2)
print(pool.has('acc1'))
pool.release('acc1')
print(pool.has('acc1'))
"
```

Expected:
```
True
True
False
```

- [ ] **Step 8.3: 提交**

```bash
git add backend/impl/jd/picker.py
git commit -m "feat(jd): picker.py _SessionPool 实现"
```

---

### Task 9: 实现 `jd_bp.py` — picker 路由

**Files:**
- Create: `backend/blueprints/jd_bp.py`

- [ ] **Step 9.1: 创建 jd_bp.py**

Create `backend/blueprints/jd_bp.py`:

```python
"""京东关联商品 picker 路由蓝图。

参考 backend/blueprints/taobao_guanghe_bp.py:
- 全局 picker event loop(后台 daemon 线程)
- 4 个路由:open / search / go_page / close
- session_id = account_id
"""

import asyncio
import logging
import threading
import time
from typing import Optional

from flask import Blueprint, request, jsonify

from backend.impl.jd.picker import pool, JdPickerSession

logger = logging.getLogger(__name__)

bp = Blueprint("jd_picker", __name__)

# ---------- 后台 event loop ----------

_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_loop_ready = threading.Event()


def _start_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop_ready.set()
    _loop.run_forever()


def _ensure_loop():
    global _loop_thread
    if _loop_thread is None or not _loop_thread.is_alive():
        _loop_ready.clear()
        _loop_thread = threading.Thread(target=_start_loop, daemon=True)
        _loop_thread.start()
        _loop_ready.wait(timeout=5)
    return _loop


def run_picker_async(coro, timeout: float = 60):
    """跨线程提交协程到 picker event loop,等待结果返回。"""
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ---------- 路由 ----------

@bp.route("/api/jd/picker/open", methods=["POST"])
def picker_open():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    if pool.has(account_id):
        return jsonify({"ok": False, "error": f"账号 {account_id} 已有 picker 在运行"}), 400

    session = pool.get_or_create(account_id)
    try:
        products = run_picker_async(session.open(), timeout=60)
        return jsonify({"ok": True, "products": products, "sessionId": account_id})
    except Exception as e:
        pool.release(account_id)
        logger.exception("picker open failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/jd/picker/search", methods=["POST"])
def picker_search():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    keyword = data.get("keyword", "")
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    session = pool.get(account_id)
    if session is None:
        return jsonify({"ok": False, "error": "picker 未打开"}), 400

    try:
        products = run_picker_async(session.search(keyword), timeout=30)
        return jsonify({"ok": True, "products": products})
    except Exception as e:
        logger.exception("picker search failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/jd/picker/go_page", methods=["POST"])
def picker_go_page():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    page = data.get("page", 1)
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    session = pool.get(account_id)
    if session is None:
        return jsonify({"ok": False, "error": "picker 未打开"}), 400

    try:
        products = run_picker_async(session.go_page(page), timeout=30)
        return jsonify({"ok": True, "products": products})
    except Exception as e:
        logger.exception("picker go_page failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/jd/picker/close", methods=["POST"])
def picker_close():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    pool.release(account_id)
    return jsonify({"ok": True})
```

- [ ] **Step 9.2: 验证 blueprint 注册**

Run:
```bash
cd backend && python -c "from blueprints.jd_bp import bp; print(bp.name, list(bp.deferred_functions) if hasattr(bp, 'deferred_functions') else len(bp.view_functions))"
```

Expected: `jd_picker 4`

- [ ] **Step 9.3: 提交**

```bash
git add backend/blueprints/jd_bp.py
git commit -m "feat(jd): jd_bp.py picker 路由蓝图"
```

---

## Phase 2: `platform.py` — 京东平台主流程

### Task 10: 实现 `platform.py` — 基础类结构 + login

**Files:**
- Create: `backend/impl/jd/platform.py`

- [ ] **Step 10.1: 创建 platform.py 骨架**

Create `backend/impl/jd/platform.py`:

```python
"""京东平台发布实现。

参考 backend/impl/taobao_guanghe/platform.py(架构平行,具体 DOM 不同)。

平台信息:
- platform_id: 20
- platform_key: 'jd'
- platform_name: '京东'
- creator_center: https://dr.jd.com/jm/
- publish_url: https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path
from queue import Queue
from typing import Optional

from backend.impl._browser import create_browser, create_context, close_browser
from backend.impl.base_platform import BasePlatform
from backend.impl.jd import _jd_link_ops as link_ops
from backend.conf import get_cookie_file_path

logger = logging.getLogger(__name__)


JD_PUBLISH_URL = "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop"
JD_CREATOR_CENTER_URL = "https://dr.jd.com/jm/"
JD_COOKIE_INVALID_HOSTS = ["passport.jd.com", "passport.shop.jd.com"]
JD_LOGIN_URL_FRAGMENT = "passport.jd.com"

JD_DRY_RUN = os.environ.get("JD_DRY_RUN", "").lower() in ("1", "true", "yes")


class JdPlatform(BasePlatform):
    """京东平台发布实现。"""

    platform_id = 20
    platform_key = "jd"
    platform_name = "京东"

    def __init__(self):
        self.browser = None
        self.page = None

    # ---------- 抽象方法 ----------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开创作中心,等待用户扫码登录。

        Args:
            id: 账号唯一标识(同 account_id)
            status_queue: 进度队列
            account_id: 数据库账号 ID(可选)
        """
        status_queue.put(("info", f"打开京东创作中心..."))

        self.browser = await create_browser(headless=False, login_mode=True)
        ctx = await self.browser.new_context()
        self.page = await ctx.new_page()

        await self.page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 等待用户完成扫码(URL 跳出 passport.* 即可)
        status_queue.put(("info", "请在浏览器中完成京东扫码登录..."))
        for _ in range(120):  # 最多 4 分钟
            await asyncio.sleep(2)
            url = self.page.url
            if JD_LOGIN_URL_FRAGMENT not in url and "dr.jd.com" in url:
                status_queue.put(("success", "登录成功"))
                break
        else:
            raise RuntimeError("京东扫码登录超时")

        # 保存 cookie
        cookie_file = get_cookie_file_path(id, self.platform_key)
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        storage = await ctx.storage_state()
        import json
        cookie_file.write_text(json.dumps(storage, ensure_ascii=False), encoding="utf-8")
        status_queue.put(("success", f"cookie 已保存到 {cookie_file}"))

        await close_browser(self.browser, is_close_by_code=True)
        self.browser = None
        self.page = None
```

- [ ] **Step 10.2: 验证 import**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform, JD_PUBLISH_URL; p = JdPlatform(); print(p.platform_id, p.platform_key, p.platform_name)"
```

Expected: `20 jd 京东`

- [ ] **Step 10.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py 基础类结构 + login 方法"
```

---

### Task 11: 实现 `platform.py` — check_cookie / sync_profile / open_creator_center

**Files:**
- Modify: `backend/impl/jd/platform.py`

- [ ] **Step 11.1: 追加账号管理方法**

Append to `backend/impl/jd/platform.py`:

```python
    async def check_cookie(self, cookie_file: str) -> bool:
        """检测 cookie 是否有效。

        策略:用 cookie 打开创作中心,如果被重定向到 passport.* → 无效。
        """
        cookie_path = Path(cookie_file)
        if not cookie_path.exists():
            return False

        browser = await create_browser(headless=True)
        try:
            ctx = await create_context(browser, storage_state=str(cookie_path))
            page = await ctx.new_page()
            await page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            url = page.url
            for invalid_host in JD_COOKIE_INVALID_HOSTS:
                if invalid_host in url:
                    logger.warning(f"京东 cookie 失效: 当前 URL {url}")
                    return False
            return True
        finally:
            await close_browser(browser, is_close_by_code=True)

    async def sync_profile(self, cookie_file: str):
        """同步账号昵称/头像。

        Returns:
            {"name": str, "avatar": str} 或 None(失败时)
        """
        cookie_path = Path(cookie_file)
        if not cookie_path.exists():
            return None

        browser = await create_browser(headless=True)
        try:
            ctx = await create_context(browser, storage_state=str(cookie_path))
            page = await ctx.new_page()
            await page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # 尝试抓取昵称(京东创作中心通常在 .user-name 或 .nickname)
            name = ""
            avatar = ""
            for sel in [".user-name", ".nickname", "[class*='name']", "[class*='user']"]:
                el = await page.query_selector(sel)
                if el:
                    txt = (await el.inner_text()).strip()
                    if txt and len(txt) < 50:
                        name = txt
                        break

            for sel in [".avatar img", ".user-avatar img", "img[src*='avatar']"]:
                el = await page.query_selector(sel)
                if el:
                    src = await el.get_attribute("src")
                    if src and "avatar" in src.lower():
                        avatar = src
                        break

            if name:
                return {"name": name, "avatar": avatar}
            return None
        except Exception as e:
            logger.warning(f"sync_profile 失败: {e}")
            return None
        finally:
            await close_browser(browser, is_close_by_code=True)

    def open_creator_center(self, cookie_file: str) -> None:
        """同步版本:打开创作中心(参考淘宝光合 L1702)。"""
        cookie_path = Path(cookie_file)
        if not cookie_path.exists():
            raise FileNotFoundError(f"cookie 文件不存在: {cookie_file}")
        asyncio.run(self._open_creator_center_async(cookie_path))

    async def _open_creator_center_async(self, cookie_path: Path):
        browser = await create_browser(headless=False)
        try:
            ctx = await create_context(browser, storage_state=str(cookie_path))
            page = await ctx.new_page()
            await page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
            # 保持打开
            await asyncio.sleep(3600)
        finally:
            await close_browser(browser, is_close_by_code=True)
```

- [ ] **Step 11.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform; p = JdPlatform(); print('check_cookie:', p.check_cookie); print('sync_profile:', p.sync_profile); print('open_creator_center:', p.open_creator_center)"
```

Expected: 三个方法名都打印

- [ ] **Step 11.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py check_cookie / sync_profile / open_creator_center"
```

---

### Task 12: 实现 `platform.py` — publish_video 主流程

**Files:**
- Modify: `backend/impl/jd/platform.py`

- [ ] **Step 12.1: 追加 publish_video 同步入口与主流程**

Append to `backend/impl/jd/platform.py`:

```python
    # ---------- 发布主流程 ----------

    def publish_video(self, **kwargs) -> bool:
        """同步入口:被 app.py 调用。

        kwargs:
            account_id: 账号 ID
            video_path: 视频文件路径
            title: 标题(必填,≤27 字)
            cover_path: 封面图路径(可选)
            jd_related_type: 'product' / 'novel' / ''
            jd_products: list[dict](含 id + trace)
            jd_novel: dict 或 ''
            jd_declaration: str
            schedule_time: str(ISO 格式)
        """
        try:
            return asyncio.run(self._publish_async(**kwargs))
        except Exception as e:
            logger.exception("京东 publish_video 失败")
            raise

    async def _publish_async(self, **kwargs) -> bool:
        """发布主流程(参考淘宝光合 platform.py L719-840)。"""
        account_id = kwargs.get("account_id")
        cookie_file = get_cookie_file_path(account_id, self.platform_key)

        if not cookie_file.exists():
            raise FileNotFoundError(f"cookie 不存在,请先登录: {cookie_file}")

        self.browser = await create_browser(headless=False)
        ctx = await create_context(self.browser, storage_state=str(cookie_file))
        self.page = await ctx.new_page()

        try:
            # 1. goto 发布页
            await self._goto_publish_page()

            # 2. 上传视频
            video_path = kwargs.get("video_path")
            if not video_path:
                raise ValueError("video_path 必填")
            await self._upload_video(Path(video_path))
            await self._wait_upload_complete()

            # 3. 设置封面(可选,京东有 * 必填但可接受默认封面)
            cover_path = kwargs.get("cover_path")
            if cover_path and Path(cover_path).exists():
                await self._set_cover(Path(cover_path))

            # 4. 填写标题
            title = kwargs.get("title", "")
            await self._fill_title(title)

            # 5. 关联挂件
            related_type = kwargs.get("jd_related_type", "")
            if related_type == "product" and kwargs.get("jd_products"):
                await self._link_products(kwargs["jd_products"])
            elif related_type == "novel" and kwargs.get("jd_novel"):
                await self._select_novel(kwargs["jd_novel"])

            # 6. 创作声明
            declaration = kwargs.get("jd_declaration", "")
            if declaration:
                await self._set_declaration(declaration)

            # 7. 定时发布
            schedule_time = kwargs.get("schedule_time", "")
            if schedule_time:
                await self._set_schedule_time(schedule_time)

            # 8. dry-run:不点发布按钮
            if JD_DRY_RUN:
                logger.info("[JD_DRY_RUN] 跳过点击发布按钮")
                return True

            # 9. 点击发布按钮
            await self._click_publish()
            return await self._check_publish_success()
        finally:
            await close_browser(self.browser, is_close_by_code=True)
            self.browser = None
            self.page = None

    async def _goto_publish_page(self):
        """goto 发布页,等表单渲染完毕。"""
        await self.page.goto(JD_PUBLISH_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self.page.wait_for_selector(
            ".video-upload-wrapper",
            timeout=15_000,
            state="visible",
        )
        await asyncio.sleep(1)
```

- [ ] **Step 12.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform; p = JdPlatform(); print('publish_video:', p.publish_video)"
```

Expected: 方法名打印

- [ ] **Step 12.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py publish_video 主流程"
```

---

### Task 13: 实现 `platform.py` — 视频上传 + 封面

**Files:**
- Modify: `backend/impl/jd/platform.py`

- [ ] **Step 13.1: 追加 _upload_video / _wait_upload_complete / _set_cover**

Append to `backend/impl/jd/platform.py`:

```python
    # ---------- 视频上传 ----------

    async def _upload_video(self, video_path: Path):
        """上传视频到 input[type=file]。

        京东发布页的 input[type=file] 在 .video-upload-wrapper 内,
        通常设置 display: none,需要通过 set_input_files 触发。
        """
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        file_input = await self.page.wait_for_selector(
            ".video-upload-wrapper input[type='file']",
            timeout=10_000,
        )
        await file_input.set_input_files(str(video_path.absolute()))

    async def _wait_upload_complete(self, timeout: float = 600):
        """等视频上传完成(进度条 DOM 隐藏)。

        上传过程中 DOM: .uploading-con > .upload-text("已上传 N%")
        上传完成:    .uploading-con 不再可见

        实现:循环检测 .uploading-con 是否消失,或 .preview-box img 出现
        """
        # 1. 等 .uploading-con 出现
        await self.page.wait_for_selector(
            ".uploading-con",
            timeout=30_000,
            state="visible",
        )
        # 2. 等 .uploading-con 消失
        await self.page.wait_for_selector(
            ".uploading-con",
            timeout=timeout * 1000,
            state="hidden",
        )
        # 3. 额外等 .preview-box img(封面预览)出现
        try:
            await self.page.wait_for_selector(
                ".preview-box img",
                timeout=30_000,
                state="visible",
            )
        except Exception:
            logger.warning("封面预览未出现,继续")

        await asyncio.sleep(1)

    # ---------- 封面 ----------

    async def _set_cover(self, cover_path: Path):
        """设置封面:点击'修改封面'按钮 → 上传本地图片 → 确定。

        1. 点 .preview-box .edit-cover-btn 打开弹窗
        2. 在弹窗内点 ._local-upload-localupload-upload-input_1vrwk_331 (input[type=file])
        3. 等缩略图加载
        4. 点弹窗确定按钮 .jd-btn-primary[data-component-label='确定']
        """
        if not cover_path.exists():
            raise FileNotFoundError(f"封面图片不存在: {cover_path}")

        # 1. 点"修改封面"
        edit_btn = await self.page.wait_for_selector(
            ".edit-cover-btn",
            timeout=10_000,
        )
        await edit_btn.click()
        await asyncio.sleep(1)

        # 2. 等弹窗出现
        await self.page.wait_for_selector(
            ".jd-modal-content",
            timeout=10_000,
            state="visible",
        )
        await self.page.wait_for_selector(
            "._crop-image_1vrwk_165 img",
            timeout=10_000,
            state="visible",
        )

        # 3. 上传本地图片(京东封面上传 input 在 ._local-upload-localupload-upload-input_1vrwk_331)
        file_input = await self.page.wait_for_selector(
            "._local-upload-localupload-upload-input_1vrwk_331",
            timeout=10_000,
        )
        await file_input.set_input_files(str(cover_path.absolute()))

        # 4. 等图片加载
        await asyncio.sleep(2)

        # 5. 点弹窗确定按钮(在 .jd-modal-footer 内)
        confirm_btn = await self.page.wait_for_selector(
            ".jd-modal-footer .jd-btn-primary",
            timeout=10_000,
        )
        await confirm_btn.click()

        # 6. 等弹窗关闭
        await self.page.wait_for_selector(
            ".jd-modal-content",
            timeout=10_000,
            state="hidden",
        )
        await asyncio.sleep(1)
```

- [ ] **Step 13.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform; p = JdPlatform(); print('_upload_video:', p._upload_video); print('_set_cover:', p._set_cover)"
```

Expected: 方法名打印

- [ ] **Step 13.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py 视频上传与封面"
```

---

### Task 14: 实现 `platform.py` — 标题

**Files:**
- Modify: `backend/impl/jd/platform.py`

- [ ] **Step 14.1: 追加 _fill_title**

Append to `backend/impl/jd/platform.py`:

```python
    # ---------- 标题 ----------

    async def _fill_title(self, title: str):
        """填写标题(最多 27 字,超长截断)。

        DOM: input#title (京东标题 input 有 id='title')
        """
        title = title.strip()[:27]  # 京东最多 27 字

        title_input = await self.page.wait_for_selector(
            "input#title",
            timeout=10_000,
        )
        await title_input.click()
        await title_input.fill("")  # 清空
        await asyncio.sleep(0.3)
        await title_input.fill(title)
        await asyncio.sleep(0.5)

        # 验证:jd-form-item-has-success 类出现
        has_success = await self.page.query_selector(
            "input#title"
        )
        if has_success:
            parent = await has_success.evaluate_handle(
                "el => el.closest('.jd-form-item')"
            )
            cls = await parent.get_property("className")
            cls_str = await cls.json_value()
            if "jd-form-item-has-success" not in cls_str:
                logger.warning(f"标题校验未通过: {cls_str}")
```

- [ ] **Step 14.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform; p = JdPlatform(); print('_fill_title:', p._fill_title)"
```

Expected: 方法名打印

- [ ] **Step 14.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py 标题填写"
```

---

### Task 15: 实现 `platform.py` — 关联商品 _link_products + _replay_products

**Files:**
- Modify: `backend/impl/jd/platform.py`

- [ ] **Step 15.1: 追加 _link_products / _replay_products**

Append to `backend/impl/jd/platform.py`:

```python
    # ---------- 关联商品 ----------

    async def _link_products(self, items: list[dict]):
        """按 trace 分组重现(参考淘宝光合 _replay_groups 但简化)。

        流程:
        1. 切商品 radio + 点添加 + 等抽屉就绪(只开一次)
        2. 按 (keyword, page) 分组
        3. 每组重走:clear_search → search → 翻页 → locate_and_check
        4. 点确定关闭抽屉
        """
        if not items:
            return

        # 1. 打开抽屉
        await link_ops.switch_radio(self.page, "product")
        await link_ops.click_add_card(self.page)
        await link_ops.wait_panel_ready(self.page)

        # 2. 分组
        groups: dict[tuple[str, int], list[dict]] = {}
        for item in items:
            trace = item.get("trace") or {}
            sig = link_ops.trace_signature(trace)
            groups.setdefault(sig, []).append(item)

        # 3. 每组重走
        for (keyword, page), group_items in groups.items():
            await link_ops.clear_search(self.page)

            if keyword:
                await link_ops.search(self.page, keyword)
                await link_ops.wait_search_results(self.page)

            if page > 1:
                # 翻到指定页
                current = await link_ops.get_current_page(self.page)
                if current < page:
                    for _ in range(page - current):
                        # 点 next 按钮
                        nxt = await self.page.query_selector(
                            ".jd-pagination-next:not(.jd-pagination-disabled)"
                        )
                        if not nxt:
                            raise RuntimeError(
                                f"无法翻到第 {page} 页:next 按钮不可用"
                            )
                        await nxt.click()
                        await link_ops.wait_page_change(self.page)
                elif current > page:
                    for _ in range(current - page):
                        prv = await self.page.query_selector(
                            ".jd-pagination-prev:not(.jd-pagination-disabled)"
                        )
                        if not prv:
                            raise RuntimeError(
                                f"无法翻到第 {page} 页:prev 按钮不可用"
                            )
                        await prv.click()
                        await link_ops.wait_page_change(self.page)

            # 4. 精准勾选
            target_ids = [it.get("id", "") for it in group_items if it.get("id")]
            if not target_ids:
                raise RuntimeError(f"商品组 (keyword={keyword!r}, page={page}) 缺少 id")

            result = await link_ops.locate_and_check(self.page, target_ids)
            if result.missing:
                raise RuntimeError(
                    f"关联商品失败,未找到商品(sku_id): {result.missing}"
                )
            if result.disabled:
                logger.warning(f"以下商品已下架,无法勾选: {result.disabled}")

        # 5. 关闭抽屉
        await link_ops.click_confirm(self.page)
```

- [ ] **Step 15.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform; p = JdPlatform(); print('_link_products:', p._link_products)"
```

Expected: 方法名打印

- [ ] **Step 15.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py 关联商品 _link_products 与分组重现"
```

---

### Task 16: 实现 `platform.py` — 关联小说 + 创作声明 + 定时发布

**Files:**
- Modify: `backend/impl/jd/platform.py`

- [ ] **Step 16.1: 追加 _select_novel / _set_declaration / _set_schedule_time**

Append to `backend/impl/jd/platform.py`:

```python
    # ---------- 关联小说 ----------

    async def _select_novel(self, novel: dict):
        """选小说(下拉搜索)。

        Args:
            novel: {"title": str, "image": str, "id": str}
        """
        # 1. 切到小说 radio
        await link_ops.switch_radio(self.page, "novel")
        await asyncio.sleep(0.5)

        # 2. 调 link_ops.select_novel(按 title 搜索)
        await link_ops.select_novel(self.page, novel.get("title", ""))

    # ---------- 创作声明 ----------

    async def _set_declaration(self, declaration: str):
        """选创作声明。

        DOM 锚点:
        - 触发:  .content-declaration-wrapper .jd-select
        - 下拉:  .rc-virtual-list-holder-inner
        - 项:    .jd-select-item-option[label='{declaration}']

        选项:
        - 含AI生成内容
        - 含虚构演绎内容
        - 内容为转载
        - 个人观点,仅供参考
        - 内容含营销广告
        - 内容无需标注
        """
        # 1. 点 .content-declaration-wrapper .jd-select
        select = await self.page.wait_for_selector(
            ".content-declaration-wrapper .jd-select",
            timeout=10_000,
        )
        await select.click()
        await asyncio.sleep(0.5)

        # 2. 等下拉出现
        await self.page.wait_for_selector(
            ".rc-virtual-list-holder-inner",
            timeout=10_000,
            state="visible",
        )
        await asyncio.sleep(0.3)

        # 3. 点对应选项(用 label 属性精确匹配)
        item_selector = (
            f".jd-select-item-option[label='{declaration}']"
        )
        item = await self.page.query_selector(item_selector)
        if not item:
            # 退而求其次:按文本匹配
            items = await self.page.query_selector_all(
                ".jd-select-item-option"
            )
            for it in items:
                lbl = await it.get_attribute("label")
                if lbl and lbl.strip() == declaration:
                    item = it
                    break
        if not item:
            raise RuntimeError(f"创作声明选项未找到: {declaration}")

        await item.click()
        await asyncio.sleep(0.5)

    # ---------- 定时发布 ----------

    async def _set_schedule_time(self, schedule_time: str):
        """设定时发布时间。

        京东定时发布:
        1. 切到 .pro-radio-group 内 value='2' 的 radio('定时发布')
        2. 点 input[title](DatePicker 输入框),清空,fill ISO 时间
        3. 在弹出的 DatePicker 中点确定按钮

        Args:
            schedule_time: ISO 格式时间字符串(如 '2026-08-14T12:26:00')
        """
        from datetime import datetime
        # 京东 DatePicker 接受 'YYYY-MM-DD HH:mm' 格式
        try:
            dt = datetime.fromisoformat(schedule_time)
            formatted = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            formatted = schedule_time

        # 1. 切到定时发布 radio
        schedule_radio = await self.page.wait_for_selector(
            ".jd-radio-wrapper input[value='2']",
            timeout=10_000,
        )
        await schedule_radio.click()
        await asyncio.sleep(0.5)

        # 2. 等 DatePicker 输入框出现
        date_input = await self.page.wait_for_selector(
            ".pro-radio-extra input[placeholder='请选择日期'], .pro-radio-extra input",
            timeout=10_000,
        )
        await date_input.click()
        await asyncio.sleep(0.3)
        await date_input.fill("")
        await asyncio.sleep(0.3)
        await date_input.fill(formatted)
        await asyncio.sleep(0.5)

        # 3. 等 DatePicker 弹层(包含"确定"按钮)
        await self.page.wait_for_selector(
            ".jd-picker-ok",
            timeout=10_000,
            state="visible",
        )

        # 4. 点确定按钮
        ok_btn = await self.page.query_selector(".jd-picker-ok .jd-btn-primary")
        if not ok_btn:
            ok_btn = await self.page.query_selector(".jd-picker-ok button")
        if not ok_btn:
            raise RuntimeError("DatePicker 确定按钮未找到")
        await ok_btn.click()
        await asyncio.sleep(1)
```

- [ ] **Step 16.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform; p = JdPlatform(); print('_select_novel:', p._select_novel); print('_set_declaration:', p._set_declaration); print('_set_schedule_time:', p._set_schedule_time)"
```

Expected: 三个方法名都打印

- [ ] **Step 16.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py 关联小说/创作声明/定时发布"
```

---

### Task 17: 实现 `platform.py` — 发布按钮 + 跳转验证

**Files:**
- Modify: `backend/impl/jd/platform.py`

- [ ] **Step 17.1: 追加 _click_publish / _check_publish_success**

Append to `backend/impl/jd/platform.py`:

```python
    # ---------- 发布 ----------

    async def _click_publish(self, timeout: float = 30):
        """点发布按钮。

        发布按钮可能因表单未完整而 disabled,需要等待其变为可点。
        """
        # 1. 等发布按钮 enabled
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            btn = await self.page.query_selector(
                "._publishBtn_6bi9b_150"
            )
            if btn:
                disabled = await btn.get_attribute("disabled")
                if disabled is None:
                    break
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError("京东发布按钮未变为可用")

        # 2. 点击
        await btn.click()

        # 3. 等弹窗(可能有发布确认对话框)
        await asyncio.sleep(2)

    async def _check_publish_success(self, timeout: float = 60) -> bool:
        """检测发布成功:URL 跳转到其他页面。

        发布成功后,京东通常跳转到 https://dr.jd.com/jm/#/n/...
        中的视频管理页或提示页。

        Returns:
            True: 发布成功
        """
        deadline = asyncio.get_event_loop().time() + timeout
        original_url = self.page.url
        while asyncio.get_event_loop().time() < deadline:
            url = self.page.url
            # 简单判定:URL 跳出发布页 hash
            if url != original_url and "publish-video.html" not in url:
                logger.info(f"京东发布成功,跳转到: {url}")
                return True
            # 检测成功提示 toast(可选)
            toast = await self.page.query_selector(
                ".jd-message-success, .ant-message-success, [class*='success']"
            )
            if toast:
                txt = (await toast.inner_text()).strip()
                if "成功" in txt or "发布" in txt:
                    logger.info(f"京东发布成功(toast): {txt}")
                    return True
            await asyncio.sleep(1)

        raise RuntimeError("京东发布失败,未检测到 URL 跳转或成功提示")
```

- [ ] **Step 17.2: 验证语法**

Run:
```bash
cd backend && python -c "from impl.jd.platform import JdPlatform; p = JdPlatform(); print('_click_publish:', p._click_publish); print('_check_publish_success:', p._check_publish_success)"
```

Expected: 两个方法名都打印

- [ ] **Step 17.3: 提交**

```bash
git add backend/impl/jd/platform.py
git commit -m "feat(jd): platform.py 发布按钮与跳转验证"
```

---

## Phase 3: 平台注册与集成

### Task 18: 注册到 `registry.py` / `app.py` / `ext_api`

**Files:**
- Modify: `backend/impl/registry.py`
- Modify: `backend/app.py`
- Modify: `backend/ext_api/__init__.py`

- [ ] **Step 18.1: 修改 registry.py 注册 JdPlatform**

Read `backend/impl/registry.py` to find `_populate_registry()`. Append:

```python
    # 20 = jd (新增)
    from backend.impl.jd.platform import JdPlatform

    register(JdPlatform)
```

- [ ] **Step 18.2: 验证注册成功**

Run:
```bash
cd backend && python -c "from impl.registry import get_platform; p = get_platform(20); print(p.platform_key, p.platform_name)"
```

Expected: `jd 京东`

- [ ] **Step 18.3: 修改 app.py 注册 jd_bp + 透传 jd 字段**

In `backend/app.py`, add near other blueprint imports:

```python
from backend.blueprints.jd_bp import bp as jd_bp
```

Add after other `app.register_blueprint(...)` calls:

```python
app.register_blueprint(jd_bp)
```

Find the 4 publish routes (search for `publish_video_platform`). In each route, add to the kwargs passed to `publish_video_platform`:

```python
    # jd 字段
    jd_related_type=data.get('jdRelatedType', ''),
    jd_products=data.get('jdProducts') or data.get('jdProductNames') or [],
    jd_novel=data.get('jdNovel', ''),
    jd_declaration=data.get('jdDeclaration', ''),
    schedule_time=data.get('scheduleTime', ''),
```

- [ ] **Step 18.4: 修改 ext_api 添加 jd 到三个 map**

In `backend/ext_api/__init__.py`, find the three maps (search for `_PLATFORM_ID_MAP`, `platform_map`, `type_to_platform`). Add:

```python
# _PLATFORM_ID_MAP
20: ('jd', '京东'),

# platform_map
'jd': '京东',

# type_to_platform
'jd': 20,
```

**注:** `_extract_channels_summary` 函数**通常不需要修改** —— 该函数按平台 group,新平台自动加入 group 即可。除非京东发布记录需要单独的字段(如 `jd_status`),否则保持现状。

- [ ] **Step 18.5: 验证 app.py 启动无报错**

Run:
```bash
cd backend && python -c "import app; print('app loaded ok')"
```

Expected: `app loaded ok`

- [ ] **Step 18.6: 提交**

```bash
git add backend/impl/registry.py backend/app.py backend/ext_api/__init__.py
git commit -m "feat(jd): 注册 JdPlatform + app.py 透传 jd 字段 + ext_api 添加 jd 映射"
```

---

## Phase 4: 前端实现

### Task 19: 创建 `jd.js` API 客户端 + 京东 logo

**Files:**
- Create: `frontend/src/api/jd.js`
- Create: `frontend/src/assets/logos/jd.png`

- [ ] **Step 19.1: 创建 jd.js**

Create `frontend/src/api/jd.js`:

```javascript
import { request } from '@/utils/request'

export const jdApi = {
  pickerOpen: (accountId) =>
    request.post('/api/jd/picker/open', { accountId }),
  pickerSearch: (accountId, keyword, page) =>
    request.post('/api/jd/picker/search', { accountId, keyword, page }),
  pickerGoPage: (accountId, page) =>
    request.post('/api/jd/picker/go_page', { accountId, page }),
  pickerClose: (accountId) =>
    request.post('/api/jd/picker/close', { accountId }),
}
```

- [ ] **Step 19.2: 添加京东 logo**

京东 logo 通常是用户提供的 PNG。如果没有现成文件,可以用占位图:

- 在 `frontend/src/assets/logos/jd.png` 放入京东 logo
- 推荐尺寸: 64x64 PNG

如果没有 logo 文件,可临时使用 jingmai.png 作为占位:

```bash
cp frontend/src/assets/logos/jingmai.png frontend/src/assets/logos/jd.png
```

后续用户替换为正式 logo 即可。

- [ ] **Step 19.3: 验证导入**

Run:
```bash
cd frontend && npx vite build --mode development
```

Expected: 不报错(`jd.js` 引用 OK)

- [ ] **Step 19.4: 提交**

```bash
git add frontend/src/api/jd.js frontend/src/assets/logos/jd.png
git commit -m "feat(jd): jd.js API 客户端 + 京东 logo"
```

---

### Task 20: 实现 `JdItemPicker.vue`

**Files:**
- Create: `frontend/src/components/JdItemPicker.vue`

- [ ] **Step 20.1: 读取 GuangheItemPicker.vue 作为模板**

Read `frontend/src/components/GuangheItemPicker.vue` carefully. 注意结构:

- Props: `modelValue`, `accountId`, `mode`, `initSelected`
- 状态: `searchKeyword`, `currentProducts`, `selectedItems`, `currentPage`, `total`
- 方法: `openPanel`, `onSearch`, `onPageChange`, `onCardClick`, `onConfirm`, `onClose`

- [ ] **Step 20.2: 创建 JdItemPicker.vue(简化版)**

Create `frontend/src/components/JdItemPicker.vue`:

```vue
<template>
  <el-dialog
    v-model="visible"
    title="关联商品 - 京东本店商品"
    width="900px"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- 搜索框 -->
    <div class="jd-picker-search">
      <el-input
        v-model="searchKeyword"
        placeholder="请输入商品名称或 skuid 搜索本店商品"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      >
        <template #append>
          <el-button @click="onSearch">搜索</el-button>
        </template>
      </el-input>
    </div>

    <!-- 已选提示 -->
    <div class="jd-picker-counter">
      已选 <strong>{{ selectedItems.length }}</strong> / 10
    </div>

    <!-- 商品列表 -->
    <div class="jd-picker-list" v-loading="loading">
      <el-empty
        v-if="!loading && currentProducts.length === 0"
        description="暂无商品"
      />
      <JdProductCard
        v-for="item in currentProducts"
        :key="item.id"
        :item="item"
        :selected="isSelected(item.id)"
        @click="onCardClick(item)"
      />
    </div>

    <!-- 分页器 -->
    <el-pagination
      v-model:current-page="currentPage"
      :page-size="10"
      :total="total"
      layout="prev, pager, next, total"
      class="jd-picker-pagination"
      @current-change="onPageChange"
    />

    <!-- 底部按钮 -->
    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button type="primary" @click="onConfirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { jdApi } from '@/api/jd'
import JdProductCard from './JdProductCard.vue'

const props = defineProps({
  modelValue: Boolean,
  accountId: String,
  initSelected: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

// 状态
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
const loading = ref(false)
const searchKeyword = ref('')
const currentProducts = ref([])
const selectedItems = ref([])
const currentPage = ref(1)
const total = ref(0)

// 打开 picker
watch(
  () => props.modelValue,
  async (val) => {
    if (val) {
      // 回显已选
      selectedItems.value = (props.initSelected || []).map(normalizeItem)
      await openPanel()
    }
  }
)

function normalizeItem(item) {
  // 兼容字符串数组(旧格式)与对象数组(新格式)
  if (typeof item === 'string') {
    return { title: item, image: '', id: '', trace: { keyword: '', page: 1 } }
  }
  return {
    title: item.title || '',
    image: item.image || '',
    id: item.id || '',
    trace: item.trace || { keyword: '', page: 1 },
  }
}

async function openPanel() {
  loading.value = true
  try {
    const resp = await jdApi.pickerOpen(props.accountId)
    if (resp.ok) {
      currentProducts.value = resp.products || []
      total.value = currentProducts.value.length > 0 ? 100 : 0
    } else {
      throw new Error(resp.error || '打开 picker 失败')
    }
  } catch (e) {
    ElMessage.error(`打开失败: ${e.message}`)
    visible.value = false
  } finally {
    loading.value = false
  }
}

async function onSearch() {
  currentPage.value = 1
  loading.value = true
  try {
    const resp = await jdApi.pickerSearch(
      props.accountId,
      searchKeyword.value,
      1
    )
    if (resp.ok) {
      currentProducts.value = resp.products || []
      total.value = Math.max(currentProducts.value.length * 10, total.value)
    }
  } finally {
    loading.value = false
  }
}

async function onPageChange(page) {
  loading.value = true
  try {
    const resp = await jdApi.pickerGoPage(props.accountId, page)
    if (resp.ok) {
      currentProducts.value = resp.products || []
    }
  } finally {
    loading.value = false
  }
}

function isSelected(id) {
  return selectedItems.value.some((s) => s.id === id)
}

function onCardClick(item) {
  const idx = selectedItems.value.findIndex((s) => s.id === item.id)
  if (idx >= 0) {
    selectedItems.value.splice(idx, 1)
  } else {
    if (selectedItems.value.length >= 10) {
      ElMessage.warning('最多选择 10 个商品')
      return
    }
    // 关键:打包 trace 快照
    selectedItems.value.push({
      title: item.title,
      image: item.image,
      id: item.id,
      trace: {
        keyword: searchKeyword.value,
        page: currentPage.value,
      },
    })
  }
}

function onConfirm() {
  emit('confirm', selectedItems.value)
  visible.value = false
}

function onClose() {
  // 释放 picker session
  if (props.accountId) {
    jdApi.pickerClose(props.accountId).catch(() => {})
  }
  visible.value = false
}
</script>

<style scoped>
.jd-picker-search {
  margin-bottom: 12px;
}
.jd-picker-counter {
  margin-bottom: 12px;
  font-size: 14px;
  color: #666;
}
.jd-picker-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  min-height: 300px;
  max-height: 500px;
  overflow-y: auto;
  padding: 8px;
  border: 1px solid #eee;
  border-radius: 4px;
}
.jd-picker-pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
```

- [ ] **Step 20.3: 创建 JdProductCard.vue 辅助组件**

Create `frontend/src/components/JdProductCard.vue`:

```vue
<template>
  <div
    class="jd-product-card"
    :class="{ selected }"
    @click="$emit('click')"
  >
    <img v-if="item.image" :src="item.image" :alt="item.title" />
    <div class="jd-product-card-title">{{ item.title }}</div>
    <div v-if="item.price" class="jd-product-card-price">{{ item.price }}</div>
    <div v-if="item.shop_name" class="jd-product-card-shop">{{ item.shop_name }}</div>
    <div class="jd-product-card-check">
      <el-icon v-if="selected"><Check /></el-icon>
    </div>
  </div>
</template>

<script setup>
import { Check } from '@element-plus/icons-vue'

defineProps({
  item: { type: Object, required: true },
  selected: Boolean,
})

defineEmits(['click'])
</script>

<style scoped>
.jd-product-card {
  position: relative;
  padding: 8px;
  border: 2px solid #eee;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}
.jd-product-card:hover {
  border-color: #409eff;
}
.jd-product-card.selected {
  border-color: #67c23a;
  background: #f0f9ff;
}
.jd-product-card img {
  width: 100%;
  height: 120px;
  object-fit: cover;
}
.jd-product-card-title {
  font-size: 13px;
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.jd-product-card-price {
  color: #e1251b;
  font-size: 14px;
  font-weight: bold;
  margin-top: 4px;
}
.jd-product-card-shop {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}
.jd-product-card-check {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  background: #67c23a;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
```

- [ ] **Step 20.4: 验证组件无语法错误**

Run:
```bash
cd frontend && npx vue-tsc --noEmit -p tsconfig.json 2>&1 | grep -i "JdItemPicker\|JdProductCard" || echo "OK"
```

Expected: `OK`

- [ ] **Step 20.5: 提交**

```bash
git add frontend/src/components/JdItemPicker.vue frontend/src/components/JdProductCard.vue
git commit -m "feat(jd): JdItemPicker.vue + JdProductCard.vue"
```

---

### Task 21: 修改 `platforms.js` 添加 JD 配置

**Files:**
- Modify: `frontend/src/config/platforms.js`

- [ ] **Step 21.1: 添加 logoJd import**

Read `frontend/src/config/platforms.js`. Add after `import logoJingmai`:

```javascript
import logoJd from '@/assets/logos/jd.png'
```

- [ ] **Step 21.2: 添加 JD 配置到 PLATFORMS**

Add at the end of `PLATFORMS` object:

```javascript
JD: {
  id: 20,
  key: 'jd',
  name: '京东',
  shortName: '京东',
  letter: '京',
  logo: logoJd,
  color: '#E1251B',
  bgColor: 'rgba(225, 37, 27, 0.15)',
  cssClass: 'jd',
  creatorUrl: 'https://dr.jd.com/jm/',
  settingsFields: [
    {
      key: 'jdDeclaration',
      label: '创作声明',
      type: 'select',
      required: false,
      options: [
        { value: '含AI生成内容', label: '含AI生成内容' },
        { value: '含虚构演绎内容', label: '含虚构演绎内容' },
        { value: '内容为转载', label: '内容为转载' },
        { value: '个人观点,仅供参考', label: '个人观点,仅供参考' },
        { value: '内容含营销广告', label: '内容含营销广告' },
        { value: '内容无需标注', label: '内容无需标注' },
      ],
    },
    { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
  ],
  defaultSettings: {
    title: '',
    description: '',
    jdRelatedType: '',
    jdProducts: [],
    jdNovel: '',
    jdDeclaration: '',
    scheduleTime: '',
  },
},
```

- [ ] **Step 21.3: 验证 platforms.js 配置生效**

Run:
```bash
cd frontend && node -e "
import('./src/config/platforms.js').then(m => {
  console.log('JD:', m.PLATFORMS.JD.id, m.PLATFORMS.JD.name);
}).catch(e => console.error(e.message));
" 2>&1 | tail -5
```

Expected: `JD: 20 京东`

- [ ] **Step 21.4: 提交**

```bash
git add frontend/src/config/platforms.js
git commit -m "feat(jd): platforms.js 添加 JD 配置"
```

---

### Task 22: 修改 `PublishCenter.vue` 适配京东

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

- [ ] **Step 22.1: 找到 PublishCenter.vue 中 taobao_guanghe 块**

Read `frontend/src/views/PublishCenter.vue`. 找到三处参考:
- L184-256 template 中 taobao_guanghe 块(关联商品/店铺设置)
- L726 import GuangheItemPicker
- L1177-1180 状态变量
- L1203-1227 openGuanghePicker / onGuanghePickerConfirm 方法

- [ ] **Step 22.2: 引入 JdItemPicker**

Add import after GuangheItemPicker import:

```javascript
import JdItemPicker from '@/components/JdItemPicker.vue'
```

- [ ] **Step 22.3: 添加京东相关状态变量**

Add after `guanghePicker*` state declarations:

```javascript
const jdPickerVisible = ref(false)
const jdPickerAccountId = ref('')
```

- [ ] **Step 22.4: 添加 openJdPicker / onJdPickerConfirm / removeJdProduct 方法**

Add after `findAnyGuangheAccountId`:

```javascript
function openJdPicker() {
  // 找到当前已勾选的京东账号
  jdPickerAccountId.value = findAnyJdAccountId('jd')
  jdPickerVisible.value = true
}

function onJdPickerConfirm(items) {
  form.value.jdProducts = items
}

function removeJdProduct(idx) {
  form.value.jdProducts.splice(idx, 1)
}

function findAnyJdAccountId(platformKey = 'jd') {
  // 从已勾选账号中找第一个京东账号
  const checked = selectedAccounts.value || []
  for (const acc of checked) {
    if (acc.platformKey === platformKey) {
      return acc.id
    }
  }
  // 退而求其次:从账号列表中找第一个京东账号
  const accounts = allAccounts.value || []
  for (const acc of accounts) {
    if (acc.platformKey === platformKey) {
      return acc.id
    }
  }
  return ''
}
```

- [ ] **Step 22.5: 添加京东专属 template 块**

Add after taobao_guanghe template block:

```vue
<template v-if="selectedPlatform === 'jd'">
  <!-- 关联挂件 radio: 不关联 / 商品 / 小说 -->
  <el-card class="platform-card" shadow="never">
    <template #header>
      <span class="card-title">关联挂件</span>
    </template>

    <el-radio-group v-model="form.jdRelatedType">
      <el-radio value="">不关联</el-radio>
      <el-radio value="product">商品</el-radio>
      <el-radio value="novel">小说</el-radio>
    </el-radio-group>

    <!-- 商品选择 -->
    <div v-if="form.jdRelatedType === 'product'" class="jd-product-list">
      <div
        v-for="(item, idx) in form.jdProducts"
        :key="item.id"
        class="jd-product-item"
      >
        <img v-if="item.image" :src="item.image" :alt="item.title" />
        <div class="jd-product-item-info">
          <div class="jd-product-item-title">{{ item.title }}</div>
        </div>
        <el-button text type="danger" @click="removeJdProduct(idx)">删除</el-button>
      </div>
      <el-button
        type="primary"
        :disabled="form.jdProducts.length >= 10"
        @click="openJdPicker"
      >
        添加商品 ({{ form.jdProducts.length }}/10)
      </el-button>
    </div>

    <!-- 小说选择(下拉搜索) -->
    <div v-if="form.jdRelatedType === 'novel'" class="jd-novel-select">
      <RemoteSearchSelect
        v-model="form.jdNovel"
        platform="jd"
        type="novel"
        :account-id="jdPickerAccountId"
      />
    </div>
  </el-card>

  <JdItemPicker
    v-model="jdPickerVisible"
    :account-id="jdPickerAccountId"
    :init-selected="form.jdProducts"
    @confirm="onJdPickerConfirm"
  />
</template>
```

- [ ] **Step 22.6: form 字段初始化确保 jd 字段存在**

在 `PublishCenter.vue` 中找到 form 初始化的位置(通常在 `data()` 或 `setup()` 中,搜索 `defaultSettings: PLATFORMS.TAOBAO_GUANGHE.defaultSettings`)。在 platform 切换逻辑处(通常在 `watch(selectedPlatform, ...)` 或 `onMounted`),添加:

```javascript
} else if (newPlatform === 'jd') {
  Object.assign(form.value, PLATFORMS.JD.defaultSettings)
}
```

**重要:** 如果 PublishCenter 没有按平台切换 defaultSettings 的逻辑,需要在 form reactive 初始化时把 JD 的 defaultSettings 合并进去,确保所有字段都有默认值,避免 `form.jdProducts` 等为 undefined 时报错。

参考光合 `L1092, L1019-1021` 的写法。

- [ ] **Step 22.7: 验证 PublishCenter 无语法错误**

Run:
```bash
cd frontend && npx vite build --mode development 2>&1 | tail -10
```

Expected: 不报错

- [ ] **Step 22.8: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(jd): PublishCenter.vue 适配京东平台"
```

---

## Phase 5: 端到端验证

### Task 23: 全流程验证清单(用户手动测试)

- [ ] **Step 23.1: 启动 dev 环境**

```bash
# 终端 1:启动后端
cd backend && python app.py

# 终端 2:启动前端
cd frontend && npm run dev
```

- [ ] **Step 23.2: 登录京东账号**

1. 打开 PublishCenter,选择京东账号
2. 点击"登录"按钮
3. 在浏览器中完成京东扫码登录
4. 确认 cookie 保存成功

- [ ] **Step 23.3: 验证视频上传与封面**

1. 上传一个测试视频(MP4, < 20G)
2. 等待进度条完成
3. (可选)上传一个 3:4 或 4:3 的封面图
4. 验证封面预览显示

- [ ] **Step 23.4: 验证关联商品 picker**

1. 关联挂件选"商品"
2. 点"添加商品"
3. 在弹窗中搜索关键词(如"小米")
4. 翻页到第 2 页
5. 选中 2-3 个商品(同关键词 + 不同关键词混合)
6. 验证 trace 字段正确打包
7. 点"确定"
8. 验证 form.jdProducts 包含完整对象(含 id + trace)

- [ ] **Step 23.5: 验证关联小说**

1. 关联挂件选"小说"
2. 在下拉搜索框中输入关键词
3. 验证下拉出现小说列表
4. 选中一个小说
5. 验证 form.jdNovel 包含 {title, image, id}

- [ ] **Step 23.6: 验证创作声明 + 定时发布**

1. 选创作声明(任选 6 种之一)
2. 设定时发布时间(未来 5 分钟后)
3. 验证定时发布 radio 已切换

- [ ] **Step 23.7: 发布并验证**

1. 标题填入测试文本(< 27 字)
2. 点"发布"
3. 观察浏览器自动操作:
   - 视频上传
   - 封面设置
   - 关联商品批量勾选(按 trace 分组重现)
   - 关联小说选择
   - 创作声明选择
   - 定时发布设置
   - 发布按钮点击
4. 验证 URL 跳转到非发布页(发布成功)

- [ ] **Step 23.8: 草稿保存/恢复**

1. 填写部分表单(标题 + 关联商品)
2. 点"保存草稿"
3. 重新打开草稿
4. 验证 form.jdProducts 完整恢复(含 id + trace)
5. 重新发布,验证仍能按 trace 分组重现

---

## 后续可能的修复

实现过程中如发现以下问题,单独 commit 修复:

1. **DOM 锚点不准确** — 京东发布页 DOM 类名带 hash 后缀(如 `_sku-card-mygoods-con_jvzh5_77`),hash 可能随版本更新变化 → 需用稳定的 `data-spm-click` 属性替代
2. **视频上传超时** — 大视频需调整 `_wait_upload_complete` 的 timeout
3. **关联商品找不到** — 京东商品 id 提取方式可能不准,需调整 `scrape_products` 和 `locate_and_check` 中的 id 提取逻辑
4. **小说下拉无结果** — 可能是 `press_sequentially` 的 delay 不足,需调整为 `delay=150` + `asyncio.sleep(2)`(参考 CLAUDE.md §6)
5. **草稿恢复后 trace 丢失** — PublishCenter 加载草稿时需读取 `form.jdProducts[].trace` 而非重新初始化

---

## Self-Review Checklist

完成所有 Task 后,逐项检查:

- [ ] 所有 14 个新增文件已创建(`backend/impl/jd/` 4 个 + `jd_bp.py` + 前端 3 个 + `assets/logos/jd.png`)
- [ ] 5 个修改文件已改(`registry.py` / `app.py` / `ext_api/__init__.py` / `platforms.js` / `PublishCenter.vue`)
- [ ] 所有 commit message 使用中文
- [ ] 后端可通过 `python -c "from impl.registry import get_platform; print(get_platform(20).platform_key)"`
- [ ] 前端 `npm run build` 无报错
- [ ] 浏览器策略:发布 headless=False,picker headless=True
- [ ] dry-run 模式 `JD_DRY_RUN=1` 可走完整流程但不点发布
- [ ] trace 模型: `{keyword: str, page: int}`,无 tab/rule/category
- [ ] 关联小说为单选(`jdNovel` 字段非数组)
- [ ] 错误处理:missing 商品 / 找不到小说 / 发布超时均有 RuntimeError