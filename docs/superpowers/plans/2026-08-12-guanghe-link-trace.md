# 淘宝光合「关联商品/店铺」轨迹快照改造 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把淘宝光合选品时的「查找轨迹」(搜索词/筛选/tab) 与每个被选商品绑定,发布时后端按轨迹分组重现路径并用 itemId/url 精准定位勾选,替代当前按完整 title 模糊匹配的不可靠方式。

**Architecture:** 抽公共 helper 模块 `_link_ops.py`(纯函数,参数为 frame),`picker.py` 和 `platform.py._link_products_or_shops` 共用同一份 DOM 操作代码。前端 `GuangheItemPicker.vue` 在卡片选中时打包当前面板状态为 trace 快照,与商品 id 一起向上传递。发布时后端按 trace 签名分组,每组「恢复 tab/筛选/搜索 → 上限 5 次加载更多内找到 itemId 就勾选」,任一商品找不到即 raise 中断。

**Tech Stack:** Python 3 / Flask / Playwright(async) / Vue 3 / Element Plus / SQLite

**Spec:** [docs/superpowers/specs/2026-08-12-guanghe-link-trace-design.md](../specs/2026-08-12-guanghe-link-trace-design.md)

---

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `backend/impl/taobao_guanghe/_link_ops.py` | 帧级 DOM 工具函数(纯函数) | 新建 |
| `backend/impl/taobao_guanghe/picker.py` | 浏览器会话池 + 业务流程 | 改造(内部调 _link_ops) |
| `backend/impl/taobao_guanghe/platform.py` | 发布平台实现,重写 `_link_products_or_shops` | 改造 |
| `backend/app.py` | 4 处 publish 路由字段名透传 | 改造 |
| `backend/tests/test_guanghe_trace_signature.py` | trace_signature 单测 | 新建 |
| `backend/tests/test_guanghe_link_ops_locate.py` | locate_and_check 单测(mock frame) | 新建 |
| `backend/tests/test_guanghe_link_group_replay.py` | 分组重现端到端单测(mock _link_ops) | 新建 |
| `frontend/src/components/GuangheItemPicker.vue` | 选品弹窗,onCardClick 时快照 trace | 改造 |
| `frontend/src/views/PublishCenter.vue` | 提交字段升级 guangheProducts/guangheShops(完整对象) | 改造 |

---

## Task 1: 新建 _link_ops.py 骨架 + trace_signature

**Files:**
- Create: `backend/impl/taobao_guanghe/_link_ops.py`
- Create: `backend/tests/test_guanghe_trace_signature.py`

- [ ] **Step 1.1: 写失败测试**

Create `backend/tests/test_guanghe_trace_signature.py`:

```python
"""trace_signature 单测 — 验证按 (tab, keyword, rule, category) 元组分组。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "impl"))

from taobao_guanghe._link_ops import trace_signature


def test_same_trace_same_signature():
    t1 = {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}
    t2 = {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}
    assert trace_signature(t1) == trace_signature(t2)


def test_different_keyword_different_signature():
    t1 = {"tab": "preferred", "keyword": "小米17", "rule": "", "category": ""}
    t2 = {"tab": "preferred", "keyword": "手机壳", "rule": "", "category": ""}
    assert trace_signature(t1) != trace_signature(t2)


def test_missing_fields_default_to_empty_string():
    t = {"tab": "shop"}
    assert trace_signature(t) == ("shop", "", "", "")


def test_empty_trace():
    assert trace_signature({}) == ("", "", "", "")


def test_grouping_use_case():
    """模拟 spec 6.3 的场景:A、B 同轨迹,C 不同。"""
    items = [
        {"id": "123", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "124", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "125", "trace": {"tab": "preferred", "keyword": "手机壳", "rule": "", "category": ""}},
    ]
    groups = {}
    for it in items:
        sig = trace_signature(it["trace"])
        groups.setdefault(sig, []).append(it["id"])
    assert len(groups) == 2
    assert groups[trace_signature(items[0]["trace"])] == ["123", "124"]
    assert groups[trace_signature(items[2]["trace"])] == ["125"]
```

- [ ] **Step 1.2: 跑测试看失败**

```bash
cd backend && python -m pytest tests/test_guanghe_trace_signature.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'taobao_guanghe._link_ops'`

- [ ] **Step 1.3: 新建 _link_ops.py**

Create `backend/impl/taobao_guanghe/_link_ops.py`:

```python
"""淘宝光合「关联商品/店铺」DOM 操作工具函数(纯函数,参数为 frame)。

picker.py 和 platform.py 共用同一份 DOM 操作代码,保证选品/发布两条路径行为一致。

设计原则:
- 所有函数都接受 frame 作为第一个参数(发布页 iframe 或主 frame)
- 不持有任何会话状态,纯 DOM 操作
- 失败时抛异常或返回空,由调用方决定如何处理
"""

from __future__ import annotations

import asyncio

# 类型常量
TYPE_PRODUCT = "product"
TYPE_SHOP = "shop"

# tab 常量(商品模式)
TAB_BOUGHT = "bought"
TAB_PREFERRED = "preferred"

# 光合发布页 URL
GUANGHE_PUBLISH_URL = (
    "https://creator.guanghe.taobao.com/page/pubNew/video"
    "?pub_url=https%3A%2F%2Fhuodong.taobao.com%2Fwow%2Fz%2Fguang%2Fgg_publish%2Fgg-video"
    "%3Fugc_scene%3Dpc_newcreator_video%26pageType%3Dvideo%26site%3Dguangguang"
    "&pub_scene=gg"
)


def trace_signature(trace: dict) -> tuple:
    """计算 trace 签名,用于发布时按状态分组复用。

    signature = (tab, keyword, rule, category)
    缺失字段视为空字符串,旧数据/店铺模式也能正常分组。
    """
    return (
        trace.get("tab", ""),
        trace.get("keyword", ""),
        trace.get("rule", ""),
        trace.get("category", ""),
    )
```

- [ ] **Step 1.4: 跑测试看通过**

```bash
cd backend && python -m pytest tests/test_guanghe_trace_signature.py -v
```

Expected: PASS(5 passed)

- [ ] **Step 1.5: Commit**

```bash
git add backend/impl/taobao_guanghe/_link_ops.py backend/tests/test_guanghe_trace_signature.py
git commit -m "feat(taobao_guanghe): 新建 _link_ops 模块骨架 + trace_signature"
```

---

## Task 2: 把 picker.py 的 DOM 操作搬到 _link_ops(重构)

把 picker.py 里的所有 DOM 操作方法搬到 _link_ops,picker session 改为调 helper。**不改变行为,纯重构**。改动较大,分 6 个 commit 落地。

**Files:**
- Modify: `backend/impl/taobao_guanghe/_link_ops.py`
- Modify: `backend/impl/taobao_guanghe/picker.py`

- [ ] **Step 2.1: 在 _link_ops 加 scrape_products(搬 picker.py:475-578)**

Edit `backend/impl/taobao_guanghe/_link_ops.py`,在文件末尾追加:

```python


# ----------------------------------------------------------------------
# 抓取 — 商品列表
# ----------------------------------------------------------------------

async def scrape_products(frame) -> tuple[list, bool]:
    """抓取当前激活 tabpanel 的商品列表。

    Returns:
        (items, has_more) — items 字段:id/title/price/image/shop_name/sold/disabled
    """
    try:
        data = await frame.evaluate(
            r"""() => {
                const out = {items: [], has_more: false};
                const panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                if (!panel) return out;
                const root = panel;

                const links = root.querySelectorAll('a[href*="item.taobao.com/item.htm"]');
                const seenCards = new Set();
                links.forEach(a => {
                    try {
                        let card = a.parentElement;
                        for (let i = 0; i < 10 && card && card !== root; i++) {
                            if (card.querySelector('label.next-checkbox-wrapper')) break;
                            card = card.parentElement;
                        }
                        if (!card || seenCards.has(card)) return;
                        seenCards.add(card);

                        const titleSpan = card.querySelector('a[href*="item.taobao.com/item.htm"] span[title], span[title]');
                        const title = titleSpan
                            ? (titleSpan.getAttribute('title') || titleSpan.textContent.trim())
                            : '';
                        const href = a.getAttribute('href') || '';
                        const m = href.match(/[?&]id=(\d+)/);
                        const itemId = m ? m[1] : '';

                        const imgs = Array.from(card.querySelectorAll('img'));
                        const mainImg = imgs.find(im => {
                            const s = im.getAttribute('src') || '';
                            return s.includes('alicdn.com');
                        }) || imgs[0];
                        const image = mainImg ? mainImg.getAttribute('src') : '';

                        let price = '';
                        const allEls = card.querySelectorAll('*');
                        for (const el of allEls) {
                            if (el.children.length > 0) continue;
                            const t = (el.textContent || '').trim();
                            if (t.startsWith('¥')) { price = t; break; }
                        }

                        let sold = '';
                        for (const el of allEls) {
                            if (el.children.length > 0) continue;
                            const t = (el.textContent || '').trim();
                            if (t.startsWith('已售')) { sold = t; break; }
                        }
                        let shopName = '';
                        const shopCandidates = Array.from(card.querySelectorAll('span, a'))
                            .map(e => (e.textContent || '').trim())
                            .filter(t => t && t !== title && !t.startsWith('¥') && !t.startsWith('已售') && t.length <= 30);
                        if (shopCandidates.length) shopName = shopCandidates[shopCandidates.length - 1];

                        const cbInput = card.querySelector('input[type="checkbox"]');
                        const disabled = cbInput ? cbInput.disabled : false;

                        if (title || image) {
                            out.items.push({
                                id: itemId || title,
                                title, price, image,
                                shop_name: shopName, sold,
                                disabled,
                            });
                        }
                    } catch (e) {}
                });

                const panelTexts = Array.from(root.querySelectorAll('span, div'))
                    .map(e => (e.textContent || '').trim());
                const hasMore = panelTexts.includes('加载更多');
                const noMore = panelTexts.includes('没有更多了');
                out.has_more = hasMore && !noMore;
                return out;
            }"""
        )
        return data.get("items", []), data.get("has_more", False)
    except Exception:
        return [], False
```

- [ ] **Step 2.2: 在 _link_ops 加 scrape_shops(搬 picker.py:580-658)**

Edit `backend/impl/taobao_guanghe/_link_ops.py`,在 `scrape_products` 之后追加:

```python


async def scrape_shops(frame) -> tuple[list, bool]:
    """抓取当前激活 tabpanel 的店铺列表。

    Returns:
        (items, has_more) — items 字段:id(=title||url)/title/image/url/buy_count/disabled
    """
    try:
        data = await frame.evaluate(
            """() => {
                const out = {items: [], has_more: false};
                const panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                if (!panel) return out;

                const radios = panel.querySelectorAll('label.next-checkbox-wrapper, label.next-radio-wrapper');
                const seen = new Set();
                radios.forEach(label => {
                    try {
                        let card = label.parentElement;
                        for (let i = 0; i < 8 && card && card !== panel; i++) {
                            if (card.querySelector('img')) break;
                            card = card.parentElement;
                        }
                        if (!card || seen.has(card)) return;
                        seen.add(card);

                        let title = '', url = '';
                        const links = Array.from(card.querySelectorAll('a'));
                        if (links.length) {
                            const longest = links.sort((a, b) =>
                                (b.textContent || '').trim().length - (a.textContent || '').trim().length
                            )[0];
                            title = (longest.textContent || '').trim();
                            url = longest.getAttribute('href') || '';
                        }

                        const img = card.querySelector('img');
                        const image = img ? img.getAttribute('src') : '';

                        let buyCount = '';
                        const allEls = card.querySelectorAll('*');
                        for (const el of allEls) {
                            if (el.children.length > 0) continue;
                            const t = (el.textContent || '').trim();
                            if (t.startsWith('已入手')) { buyCount = t; break; }
                        }

                        const rInput = card.querySelector('input[type="radio"], input[type="checkbox"]');
                        const disabled = rInput ? rInput.disabled : false;

                        if (title || image) {
                            out.items.push({
                                id: title || url,
                                title, image, url,
                                buy_count: buyCount,
                                disabled,
                            });
                        }
                    } catch (e) {}
                });

                const allText = Array.from(panel.querySelectorAll('span, div'))
                    .map(e => (e.textContent || '').trim());
                const hasMore = allText.includes('加载更多');
                const noMore = allText.includes('没有更多了');
                out.has_more = hasMore && !noMore;
                return out;
            }"""
        )
        return data.get("items", []), data.get("has_more", False)
    except Exception:
        return [], False


async def scrape(frame, type_: str) -> tuple[list, bool]:
    """分发到 scrape_products/scrape_shops。"""
    if type_ == TYPE_PRODUCT:
        return await scrape_products(frame)
    return await scrape_shops(frame)
```

- [ ] **Step 2.3: 在 _link_ops 加 scrape_filters(搬 picker.py:419-467)**

Edit `backend/impl/taobao_guanghe/_link_ops.py`,在 `scrape` 之后追加:

```python


async def scrape_filters(frame) -> dict:
    """抓推荐规则/品类选项(仅商品模式有效)。

    Returns:
        {"rules": [...], "categories": [...]}
    """
    try:
        data = await frame.evaluate(
            """() => {
                const out = {rules: [], categories: []};
                const panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                if (!panel) return out;

                function getOptions(labelPrefix) {
                    const leaves = Array.from(panel.querySelectorAll('*')).filter(el => {
                        if (el.children.length > 0) return false;
                        const t = (el.textContent || '').trim();
                        return t.startsWith(labelPrefix);
                    });
                    if (!leaves.length) return [];
                    const label = leaves[0];
                    let group = label.nextElementSibling;
                    if (!group) group = label.parentElement;
                    if (!group) return [];
                    const opts = [];
                    group.querySelectorAll('*').forEach(o => {
                        if (o.children.length > 0) return;
                        const t = (o.textContent || '').trim();
                        if (t && !t.startsWith(labelPrefix)) opts.push(t);
                    });
                    return opts;
                }

                out.rules = getOptions('推荐规则');
                out.categories = getOptions('品类筛选');
                return out;
            }"""
        )
        return data or {"rules": [], "categories": []}
    except Exception:
        return {"rules": [], "categories": []}
```

- [ ] **Step 2.4: 在 _link_ops 加面板操作(switch_radio/click_add_card/wait_panel_ready/switch_tab/click_filter/search/load_more)**

Edit `backend/impl/taobao_guanghe/_link_ops.py`,在 `scrape_filters` 之后追加:

```python


# ----------------------------------------------------------------------
# 面板操作
# ----------------------------------------------------------------------

async def switch_radio(frame, type_: str) -> None:
    """切换商品/店铺 radio(.next-radio-label + 文本)。"""
    target_label = "商品" if type_ == TYPE_PRODUCT else "店铺"
    radio_label = frame.locator(f'.next-radio-label:has-text("{target_label}")').first
    await radio_label.wait_for(state="visible", timeout=10000)
    is_checked = await radio_label.evaluate(
        "el => el.closest('label')?.classList.contains('checked')"
    )
    if not is_checked:
        await radio_label.click()
        await asyncio.sleep(0.8)


async def click_add_card(frame, type_: str) -> None:
    """点击「添加商品/店铺」卡片打开选择面板。"""
    trigger_text = "添加商品" if type_ == TYPE_PRODUCT else "添加店铺"
    trigger = frame.get_by_text(trigger_text, exact=True).first
    await trigger.wait_for(state="visible", timeout=8000)
    await trigger.click()
    await asyncio.sleep(2)


async def wait_panel_ready(frame, type_: str) -> None:
    """等待选择面板就绪(商品:等 tab;店铺:等搜索框)。"""
    if type_ == TYPE_PRODUCT:
        await frame.locator(
            '.next-tabs-tab:has-text("已购商品"), .next-tabs-tab:has-text("平台优选")'
        ).first.wait_for(state="visible", timeout=10000)
    else:
        await frame.locator('input[placeholder*="店铺"]').first.wait_for(
            state="visible", timeout=10000
        )


async def switch_tab(frame, tab: str) -> None:
    """切换 bought/preferred tab(仅商品模式)。"""
    if tab not in (TAB_BOUGHT, TAB_PREFERRED):
        return
    target_text = "已购商品" if tab == TAB_BOUGHT else "平台优选"
    try:
        tab_el = frame.locator(f'.next-tabs-tab:has-text("{target_text}")').first
        await tab_el.wait_for(state="visible", timeout=5000)
    except Exception:
        return

    is_active = await tab_el.evaluate("el => el.classList.contains('active')")
    if is_active:
        return
    await tab_el.click()
    try:
        await frame.wait_for_function(
            """(text) => {
                const tabs = document.querySelectorAll('.next-tabs-tab');
                return [...tabs].some(t =>
                    (t.textContent || '').includes(text) && t.classList.contains('active')
                );
            }""",
            target_text,
            timeout=5000,
        )
    except Exception:
        pass
    await asyncio.sleep(1.2)


async def click_filter(frame, row_label: str, option_text: str) -> None:
    """点击筛选选项(row_label='推荐规则'/'品类筛选')。"""
    panel = frame.locator('[role="tabpanel"][aria-hidden="false"]')
    label_el = panel.get_by_text(row_label, exact=False).first
    if await label_el.count() == 0:
        return
    await label_el.evaluate(
        """(el, optText) => {
            let row = el.parentElement;
            for (let i = 0; i < 5 && row; i++) {
                const all = row.querySelectorAll('*');
                for (const o of all) {
                    if (o === el) continue;
                    if (o.children.length > 0) continue;
                    const t = (o.textContent || '').trim();
                    if (t === optText) {
                        const classes = [...o.classList, ...(o.parentElement?.classList || [])];
                        const isActive = classes.some(c => c === 'active' || c.endsWith('-active--'));
                        if (isActive) return;
                        o.click();
                        return;
                    }
                }
                row = row.parentElement;
            }
        }""",
        option_text,
    )
    await asyncio.sleep(1.2)


async def search(frame, keyword: str) -> None:
    """搜索框输入并回车。空 keyword 视为清空。"""
    panel = frame.locator('[role="tabpanel"][aria-hidden="false"]')
    inp = panel.locator('input[role="searchbox"]').first
    await inp.wait_for(state="visible", timeout=5000)
    await inp.click()
    await inp.fill("")
    if keyword:
        await inp.fill(keyword)
    await asyncio.sleep(0.3)
    await inp.press("Enter")
    await asyncio.sleep(1.5)


async def load_more(frame) -> bool:
    """点「加载更多」,返回是否实际点击(无更多时返回 False)。"""
    more_btn = frame.get_by_text("加载更多", exact=True).first
    if await more_btn.count() > 0:
        try:
            await more_btn.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        await more_btn.click()
        await asyncio.sleep(2)
        return True
    return False
```

- [ ] **Step 2.5: picker.py 删除被搬走的方法,改调 _link_ops**

Edit `backend/impl/taobao_guanghe/picker.py`:

1. **修改 import**(在文件顶部 `from .._browser import create_browser, create_context` 之后追加):

```python
from . import _link_ops
```

2. **删除常量** `_GUANGHE_PUBLISH_URL`、`_TYPE_PRODUCT`、`_TYPE_SHOP`(已搬到 _link_ops),改为引用:

```python
from ._link_ops import GUANGHE_PUBLISH_URL as _GUANGHE_PUBLISH_URL
from ._link_ops import TYPE_PRODUCT as _TYPE_PRODUCT
from ._link_ops import TYPE_SHOP as _TYPE_SHOP
```

3. **替换 `open` 方法的 goto URL**(原本引用 `_GUANGHE_PUBLISH_URL`,常量名不变,无需改动)

4. **替换 `switch_tab` 方法**(picker.py:160-204) — 改为调 helper:

```python
    async def switch_tab(self, tab: str) -> dict:
        """商品模式:切换「已购商品」/「平台优选」。"""
        if self.current_type != "product":
            raise RuntimeError("tab 切换仅商品模式支持")
        if tab not in ("bought", "preferred"):
            raise ValueError(f"unknown tab: {tab}")
        target_text = "已购商品" if tab == "bought" else "平台优选"
        logger.info(f"[Picker][{self.session_id}] switch_tab → {target_text}")
        await _link_ops.switch_tab(self.frame, tab)
        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more}
```

5. **替换 `apply_filter` 方法**(picker.py:206-228):

```python
    async def apply_filter(self, rule: str | None = None, category: str | None = None) -> dict:
        """切换推荐规则/品类筛选(仅平台优选 tab 有效)。"""
        if self.current_type != "product":
            raise RuntimeError("筛选仅商品模式支持")
        if rule:
            await _link_ops.click_filter(self.frame, "推荐规则", rule)
        if category:
            await _link_ops.click_filter(self.frame, "品类筛选", category)
        await asyncio.sleep(1.2)
        items, has_more = await self._scrape()
        filters = await self._scrape_filters()
        return {"items": items, "has_more": has_more, "filters": filters}
```

6. **替换 `search` 方法**(picker.py:230-254):

```python
    async def search(self, keyword: str) -> dict:
        """搜索。"""
        keyword = (keyword or "").strip()
        logger.info(f"[Picker][{self.session_id}] search: {keyword!r}")
        await _link_ops.search(self.frame, keyword)
        items, has_more = await self._scrape()
        filters = await self._scrape_filters() if self.current_type == "product" else {}
        return {"items": items, "has_more": has_more, "filters": filters}
```

7. **替换 `load_more` 方法**(picker.py:256-284):

```python
    async def load_more(self) -> dict:
        """点击「加载更多」按钮。"""
        logger.info(f"[Picker][{self.session_id}] load_more")
        await _link_ops.load_more(self.frame)
        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more}
```

8. **替换 `_open_picker_panel` 方法**(picker.py:313-366):

```python
    async def _open_picker_panel(self, type_: str) -> None:
        """在发布页 iframe 内:点对应 radio → 点添加卡片 → 等选择面板出现。"""
        frame = self.frame
        try:
            await _link_ops.switch_radio(frame, type_)
            logger.info(f"[Picker] ✓ 已选 radio={'商品' if type_ == 'product' else '店铺'}")
        except Exception as e:
            logger.info(f"[Picker] radio 点击失败: {e}")

        try:
            await _link_ops.click_add_card(frame, type_)
            trigger_text = "添加商品" if type_ == "product" else "添加店铺"
            logger.info(f"[Picker] ✓ 已点击 {trigger_text}")
        except Exception as e:
            logger.info(f"[Picker] 添加卡片点击失败: {e}")

        try:
            await _link_ops.wait_panel_ready(frame, type_)
            if type_ == "product":
                await self.switch_tab("preferred")
        except Exception as e:
            logger.info(f"[Picker] 面板等待失败: {e}")
```

9. **删除 `_click_filter_option`、`_scrape_filters`、`_scrape_products`、`_scrape_shops` 方法**(picker.py:368-658),把 `_scrape` 改为调 helper:

```python
    async def _scrape(self) -> tuple[list, bool]:
        """抓取当前面板所有商品/店铺。"""
        return await _link_ops.scrape(self.frame, self.current_type)

    async def _scrape_filters(self) -> dict:
        """抓取筛选选项。"""
        return await _link_ops.scrape_filters(self.frame)
```

- [ ] **Step 2.6: 验证 picker 改造无回归**

启动后端,打开淘宝光合选品弹窗,完整跑一遍「打开 → 切商品/店铺 → 切 tab → 筛选 → 搜索 → 加载更多 → 关闭」流程,日志应与改造前一致。

```bash
cd backend && python app.py
```

(手动验证后端能正常启动,picker API 无报错)

- [ ] **Step 2.7: Commit**

```bash
git add backend/impl/taobao_guanghe/_link_ops.py backend/impl/taobao_guanghe/picker.py
git commit -m "refactor(taobao_guanghe): picker.py DOM 操作搬到 _link_ops"
```

---

## Task 3: _link_ops.locate_and_check 实现

新增核心函数:在当前列表里按 id 集合定位并勾选。

**Files:**
- Modify: `backend/impl/taobao_guanghe/_link_ops.py`
- Create: `backend/tests/test_guanghe_link_ops_locate.py`

- [ ] **Step 3.1: 写失败测试**

Create `backend/tests/test_guanghe_link_ops_locate.py`:

```python
"""locate_and_check 单测 — mock frame 验证匹配/勾选/disabled 逻辑。

同步测试风格(与现有 backend/tests/ 一致),async 函数用 asyncio.run 包一层。
不依赖 pytest-asyncio。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "impl"))

from taobao_guanghe import _link_ops  # noqa: E402


def _patch(func_name, fake_coro):
    """把 _link_ops.<func_name> 临时替换为 fake_coro(同步函数返回 dict)。"""
    original = getattr(_link_ops, func_name)
    setattr(_link_ops, func_name, fake_coro)
    return original


def test_all_targets_clicked():
    """三个目标都命中且 clicked。"""
    fake_items = [
        {"id": "111", "title": "A1", "disabled": False},
        {"id": "222", "title": "A2", "disabled": False},
        {"id": "333", "title": "A3", "disabled": False},
    ]
    orig_scrape = _patch("scrape", lambda frame, type_: (fake_items[:], False))

    async def fake_click(frame, type_, tid):
        return "clicked"
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111", "222", "333"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert set(result["checked"]) == {"111", "222", "333"}
    assert result["already"] == []
    assert result["disabled"] == []
    assert result["missing"] == []


def test_some_missing():
    """列表里只有 111/222,999 找不到。"""
    fake_items = [{"id": "111", "disabled": False}, {"id": "222", "disabled": False}]
    orig_scrape = _patch("scrape", lambda frame, type_: (fake_items[:], False))

    async def fake_click(frame, type_, tid):
        return "clicked" if tid in {"111", "222"} else "not_found"
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111", "222", "999"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert set(result["checked"]) == {"111", "222"}
    assert result["missing"] == ["999"]


def test_disabled_item_reported():
    """目标在列表里但 disabled=True → 进 disabled 桶,不调 click。"""
    fake_items = [{"id": "111", "disabled": True}]

    async def fake_click(frame, type_, tid):
        raise AssertionError("disabled item 不应该走到 click")
    orig_scrape = _patch("scrape", lambda frame, type_: (fake_items[:], False))
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert result["disabled"] == ["111"]
    assert result["checked"] == []


def test_already_checked():
    """已勾选的算 already,不重复 click。"""
    fake_items = [{"id": "111", "disabled": False}]
    orig_scrape = _patch("scrape", lambda frame, type_: (fake_items[:], False))

    async def fake_click(frame, type_, tid):
        return "already"
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert result["already"] == ["111"]
    assert result["checked"] == []
```

**前置依赖**:需要安装 pytest(开发依赖,不在 requirements.txt 里)。如果环境已装可跳过:

```bash
pip install pytest
```

- [ ] **Step 3.2: 跑测试看失败**

```bash
cd backend && python -m pytest tests/test_guanghe_link_ops_locate.py -v
```

Expected: FAIL with `AttributeError: module '_link_ops' has no attribute 'locate_and_check'`

- [ ] **Step 3.3: 在 _link_ops 加 _click_item_by_id 和 locate_and_check**

Edit `backend/impl/taobao_guanghe/_link_ops.py`,在 `load_more` 之后追加:

```python


# ----------------------------------------------------------------------
# 定位并勾选
# ----------------------------------------------------------------------

async def _click_item_by_id(frame, type_: str, item_id: str) -> str:
    """在当前面板内找 id=item_id 的商品/店铺并勾选。

    Returns:
        'clicked'    — 本次新勾选
        'already'    — 已勾选
        'disabled'   — 找到但禁用
        'not_found'  — 未找到
    """
    result = await frame.evaluate(
        """(args) => {
            const { id, type } = args;
            const panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
            if (!panel) return 'not_found';

            // 商品锚点:a[href*="item.taobao.com"][href*="id=<itemId>"]
            // 店铺锚点:文本/链接含 id 的卡片
            let anchors = [];
            if (type === 'product') {
                anchors = Array.from(panel.querySelectorAll('a[href*="item.taobao.com/item.htm"]'))
                    .filter(a => (a.getAttribute('href') || '').includes('id=' + id));
            } else {
                // 店铺 id 可能是 title 或 url(见 _link_ops.scrape_shops)
                anchors = Array.from(panel.querySelectorAll('a'))
                    .filter(a => {
                        const href = a.getAttribute('href') || '';
                        const text = (a.textContent || '').trim();
                        return href.includes(id) || text === id;
                    });
            }

            const checkboxSelector = type === 'product'
                ? 'label.next-checkbox-wrapper'
                : 'label.next-radio-wrapper, label.next-checkbox-wrapper';

            for (const anchor of anchors) {
                let node = anchor;
                for (let i = 0; i < 10 && node; i++) {
                    const label = node.querySelector && node.querySelector(checkboxSelector);
                    if (label) {
                        const input = label.querySelector('input[type="checkbox"], input[type="radio"]');
                        if (input && input.disabled) return 'disabled';
                        const isChecked = label.classList.contains('checked')
                            || (input && input.checked);
                        if (isChecked) return 'already';
                        label.click();
                        return 'clicked';
                    }
                    node = node.parentElement;
                }
            }
            return 'not_found';
        }""",
        {"id": item_id, "type": type_},
    )
    return result


async def locate_and_check(frame, type_: str, target_ids: set) -> dict:
    """在当前列表里定位并勾选目标 id。

    Args:
        frame: 发布页 iframe
        type_: 'product' / 'shop'
        target_ids: 待勾选的 id 字符串集合

    Returns:
        {
            "checked":  [id, ...],  # 本次新勾选
            "already":  [id, ...],  # 已勾选(无需点击)
            "disabled": [id, ...],  # 找到但禁用(中断信号)
            "missing":  [id, ...],  # 未找到(可继续加载更多)
        }
    """
    items, _ = await scrape(frame, type_)
    found = {str(it.get("id", "")): it for it in items}

    result = {"checked": [], "already": [], "disabled": [], "missing": []}
    for tid in target_ids:
        tid_str = str(tid)
        item = found.get(tid_str)
        if item is None:
            result["missing"].append(tid_str)
            continue
        if item.get("disabled"):
            result["disabled"].append(tid_str)
            continue
        click_res = await _click_item_by_id(frame, type_, tid_str)
        if click_res == "clicked":
            result["checked"].append(tid_str)
        elif click_res == "already":
            result["already"].append(tid_str)
        elif click_res == "disabled":
            result["disabled"].append(tid_str)
        else:
            result["missing"].append(tid_str)
    return result
```

- [ ] **Step 3.4: 跑测试看通过**

```bash
cd backend && python -m pytest tests/test_guanghe_link_ops_locate.py -v
```

Expected: PASS(4 passed)

- [ ] **Step 3.5: Commit**

```bash
git add backend/impl/taobao_guanghe/_link_ops.py backend/tests/test_guanghe_link_ops_locate.py
git commit -m "feat(taobao_guanghe): _link_ops.locate_and_check 按 itemId/url 精准定位勾选"
```

---

## Task 4: 重写 platform._link_products_or_shops(分组重现 + 中断策略)

**Files:**
- Modify: `backend/impl/taobao_guanghe/platform.py` (替换 `_link_products_or_shops` 方法 + `_upload_single_video` 调用 + `publish_video` 字段读取)
- Create: `backend/tests/test_guanghe_link_group_replay.py`

- [ ] **Step 4.1: 写失败测试(分组重现 + 5 次上限 + raise)**

Create `backend/tests/test_guanghe_link_group_replay.py`:

```python
"""_replay_groups 分组重现 + 中断策略 单测。

同步测试风格,async 用 asyncio.run 包一层。mock _link_ops 模块级函数。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "impl"))

from taobao_guanghe import _link_ops
# platform 模块在导入时会初始化 logger,但不会启动浏览器
from impl.taobao_guanghe import platform as platform_mod


def _patch_all(fake_scrape_items, click_results=None, load_more_returns=True):
    """统一 patch _link_ops 模块级函数,返回还原函数。"""
    click_results = click_results or {}

    async def fake_scrape(frame, type_):
        return fake_scrape_items[:], False

    async def fake_click_item(frame, type_, tid):
        return click_results.get(tid, "clicked")

    async def fake_load_more(frame):
        return load_more_returns

    async def fake_noop(*a, **kw):
        pass

    saved = {
        "scrape": _link_ops.scrape,
        "_click_item_by_id": _link_ops._click_item_by_id,
        "load_more": _link_ops.load_more,
        "switch_radio": _link_ops.switch_radio,
        "click_add_card": _link_ops.click_add_card,
        "wait_panel_ready": _link_ops.wait_panel_ready,
        "switch_tab": _link_ops.switch_tab,
        "click_filter": _link_ops.click_filter,
        "search": _link_ops.search,
    }
    _link_ops.scrape = fake_scrape
    _link_ops._click_item_by_id = fake_click_item
    _link_ops.load_more = fake_load_more
    _link_ops.switch_radio = fake_noop
    _link_ops.click_add_card = fake_noop
    _link_ops.wait_panel_ready = fake_noop
    _link_ops.switch_tab = fake_noop
    _link_ops.click_filter = fake_noop
    _link_ops.search = fake_noop

    def restore():
        for k, v in saved.items():
            setattr(_link_ops, k, v)

    return restore


def _make_confirm_visible_false():
    """mock frame,confirm 按钮 count=0(不进点击分支)。"""
    frame = MagicMock()
    confirm_btn = MagicMock()
    confirm_btn.count = MagicMock(return_value=0)
    frame.locator.return_value.first = confirm_btn
    return frame


def test_group_replay_basic():
    """两组 trace,所有 itemId 都命中即 clicked,不应 raise。"""
    fake_items = [
        {"id": "111", "disabled": False},
        {"id": "222", "disabled": False},
        {"id": "333", "disabled": False},
    ]
    link_items = [
        {"id": "111", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "222", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "333", "trace": {"tab": "preferred", "keyword": "手机壳", "rule": "", "category": ""}},
    ]
    restore = _patch_all(fake_items)
    frame = _make_confirm_visible_false()
    try:
        # 不应 raise
        asyncio.run(platform_mod._replay_groups(frame, "product", link_items, max_load_more=5))
    finally:
        restore()


def test_raise_when_disabled():
    """目标商品 disabled → raise RuntimeError,消息含「不可选」。"""
    fake_items = [{"id": "111", "disabled": True}]
    link_items = [{"id": "111", "trace": {"tab": "preferred", "keyword": "x"}}]
    restore = _patch_all(fake_items)
    frame = _make_confirm_visible_false()
    try:
        try:
            asyncio.run(platform_mod._replay_groups(frame, "product", link_items, max_load_more=5))
            assert False, "应抛 RuntimeError"
        except RuntimeError as e:
            assert "不可选" in str(e)
    finally:
        restore()


def test_raise_when_not_found_after_max_load_more():
    """超过 max_load_more 仍未找到 → raise,消息含「未找到」。"""
    fake_items = []  # 永远空
    link_items = [{"id": "999", "trace": {"tab": "preferred", "keyword": "x"}}]
    restore = _patch_all(fake_items, load_more_returns=True)
    frame = _make_confirm_visible_false()
    try:
        try:
            asyncio.run(platform_mod._replay_groups(frame, "product", link_items, max_load_more=5))
            assert False, "应抛 RuntimeError"
        except RuntimeError as e:
            assert "未找到" in str(e)
            assert "999" in str(e)
    finally:
        restore()
```

- [ ] **Step 4.2: 跑测试看失败**

```bash
cd backend && python -m pytest tests/test_guanghe_link_group_replay.py -v
```

Expected: FAIL with `ImportError: cannot import name '_replay_groups'`

- [ ] **Step 4.3: 在 platform.py 加 _replay_groups + 重写 _link_products_or_shops**

Edit `backend/impl/taobao_guanghe/platform.py`:

1. **顶部 import**(在 `from ..base_platform import BasePlatform` 之后追加):

```python
from . import _link_ops
```

2. **在 `class TaobaoGuanghePlatform` 之前**(模块级,放在 `_CLAIM_OPTIONS` 之后)添加纯逻辑函数:

```python
# ----------------------------------------------------------------------
# 分组重现 + 中断策略(纯逻辑,可单测)
# ----------------------------------------------------------------------

# 旧数据兼容:无 trace 时退回按 title 模糊匹配
_LEGACY_FALLBACK_THRESHOLD = 5  # 旧路径加载更多上限


def _group_by_trace(items: list) -> list:
    """按 trace_signature 分组,返回 [(trace, [item, ...]), ...]。"""
    groups = {}
    order = []
    for it in items:
        tr = it.get("trace") or {}
        sig = _link_ops.trace_signature(tr)
        if sig not in groups:
            groups[sig] = {"trace": tr, "items": []}
            order.append(sig)
        groups[sig]["items"].append(it)
    return [(groups[sig]["trace"], groups[sig]["items"]) for sig in order]


async def _replay_groups(frame, type_: str, items: list, max_load_more: int = 5) -> None:
    """按 trace 分组重现并精准定位勾选。

    Args:
        frame: 发布页 iframe
        type_: 'product' / 'shop'
        items: [{id, trace, title?, ...}, ...]
        max_load_more: 每组最多点几次加载更多

    Raises:
        RuntimeError: 任一商品 disabled 或 max_load_more 后仍未找到
    """
    # 兼容旧数据:items 不含 trace 时走旧路径
    if any(not it.get("trace") for it in items):
        await _legacy_link_by_title(frame, type_, items)
        return

    type_label = "商品" if type_ == "product" else "店铺"
    groups = _group_by_trace(items)
    logger.info(f"[关联{type_label}] 共 {len(items)} 个,{len(groups)} 组轨迹")

    for gi, (trace, group_items) in enumerate(groups, 1):
        target_ids = {str(it["id"]) for it in group_items if it.get("id")}
        logger.info(
            f"[关联{type_label}] 组 {gi}/{len(groups)}: tab={trace.get('tab')} "
            f"kw={trace.get('keyword')!r} rule={trace.get('rule')!r} "
            f"category={trace.get('category')!r} → {len(target_ids)} 个目标"
        )

        # 1. 切 radio + 打开面板
        await _link_ops.switch_radio(frame, type_)
        await _link_ops.click_add_card(frame, type_)
        await _link_ops.wait_panel_ready(frame, type_)

        # 2. 切 tab(商品模式)
        if type_ == "product" and trace.get("tab"):
            await _link_ops.switch_tab(frame, trace["tab"])

        # 3. 筛选(商品模式)
        if type_ == "product":
            if trace.get("rule"):
                await _link_ops.click_filter(frame, "推荐规则", trace["rule"])
            if trace.get("category"):
                await _link_ops.click_filter(frame, "品类筛选", trace["category"])

        # 4. 搜索
        if trace.get("keyword"):
            await _link_ops.search(frame, trace["keyword"])

        # 5. 循环定位 + 加载更多
        pending = set(target_ids)
        for attempt in range(max_load_more + 1):  # 首次 + 5 次加载更多
            res = await _link_ops.locate_and_check(frame, type_, pending)
            if res["disabled"]:
                raise RuntimeError(
                    f"商品不可选(disabled): {res['disabled']}"
                )
            for tid in res["checked"] + res["already"]:
                pending.discard(tid)
            if not pending:
                logger.info(
                    f"[关联{type_label}] 组 {gi} ✓ 勾选完成 "
                    f"(尝试 {attempt + 1} 次)"
                )
                break
            if attempt < max_load_more:
                clicked = await _link_ops.load_more(frame)
                if not clicked:
                    break  # 没有加载更多按钮
            else:
                break

        if pending:
            raise RuntimeError(
                f"未找到的{type_label} id(超过 {max_load_more} 次加载更多): "
                f"{sorted(pending)}"
            )

        # 6. 点确定关闭面板(为下一组准备)
        try:
            confirm_btn = frame.locator(
                '.next-btn-primary:has-text("确定"), '
                '.next-btn-primary:has-text("完成"), '
                '.next-btn-primary:has-text("确认")'
            ).first
            if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
                await confirm_btn.click()
                await asyncio.sleep(1.5)
        except Exception as e:
            logger.info(f"[关联{type_label}] 确定按钮异常: {e}")


async def _legacy_link_by_title(frame, type_: str, items: list) -> None:
    """旧路径:按 title 搜+span[title] 匹配(无 trace 数据时用)。"""
    type_label = "商品" if type_ == "product" else "店铺"
    logger.info(f"[关联{type_label}] 检测到旧格式数据,退回 title 匹配路径")
    names = [(it.get("title") or "").strip() for it in items if it.get("title")]
    if not names:
        return

    # 切 radio + 打开面板
    try:
        radio_label = frame.locator(f'.next-radio-label:has-text("{type_label}")').first
        await radio_label.wait_for(state="visible", timeout=10000)
        is_checked = await radio_label.evaluate(
            "el => el.closest('label')?.classList.contains('checked')"
        )
        if not is_checked:
            await radio_label.click()
            await asyncio.sleep(0.8)
    except Exception as e:
        logger.info(f"[关联{type_label}] radio 切换失败: {e}")
        return

    trigger_text = "添加商品" if type_ == "product" else "添加店铺"
    try:
        trigger = frame.get_by_text(trigger_text, exact=True).first
        await trigger.wait_for(state="visible", timeout=8000)
        await trigger.click()
        await asyncio.sleep(2)
    except Exception as e:
        logger.info(f"[关联{type_label}] 添加卡点击失败: {e}")
        return

    if type_ == "product":
        try:
            tab = frame.locator('.next-tabs-tab:has-text("平台优选")').first
            if await tab.count() > 0:
                is_active = await tab.evaluate("el => el.classList.contains('active')")
                if not is_active:
                    await tab.click()
                    await asyncio.sleep(1.5)
        except Exception:
            pass

    selected = 0
    for idx, name in enumerate(names, 1):
        try:
            inp = frame.locator('input[role="searchbox"]').first
            await inp.wait_for(state="visible", timeout=5000)
            await inp.click()
            await inp.fill("")
            await inp.fill(name)
            await asyncio.sleep(0.3)
            await inp.press("Enter")
            await asyncio.sleep(2)

            result = await frame.evaluate(
                """(args) => {
                    const { name, type } = args;
                    const checkboxSelector = type === 'product'
                        ? 'label.next-checkbox-wrapper'
                        : 'label.next-radio-wrapper';
                    let anchors = [];
                    if (type === 'product') {
                        anchors = Array.from(document.querySelectorAll('span[title]'))
                            .filter(s => (s.getAttribute('title') || '').trim() === name);
                    } else {
                        anchors = Array.from(document.querySelectorAll('a'))
                            .filter(a => (a.textContent || '').trim() === name);
                    }
                    for (const anchor of anchors) {
                        let node = anchor;
                        for (let i = 0; i < 10 && node; i++) {
                            const label = node.querySelector && node.querySelector(checkboxSelector);
                            if (label) {
                                const input = label.querySelector('input[type="checkbox"], input[type="radio"]');
                                if (input && input.disabled) return 'disabled';
                                const isChecked = label.classList.contains('checked')
                                    || (input && input.checked);
                                if (!isChecked) { label.click(); return 'clicked'; }
                                return 'already';
                            }
                            node = node.parentElement;
                        }
                    }
                    return 'not_found';
                }""",
                {"name": name, "type": type_},
            )
            if result in ("clicked", "already"):
                selected += 1
                logger.info(f"[关联{type_label}] ({idx}/{len(names)}) ✓ {name} ({result})")
            else:
                raise RuntimeError(f"未找到匹配: {name} ({result})")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"关联异常({name}): {e}")

    logger.info(f"[关联{type_label}] 旧路径勾选完成 {selected}/{len(names)}")
    try:
        confirm_btn = frame.locator(
            '.next-btn-primary:has-text("确定"), '
            '.next-btn-primary:has-text("完成"), '
            '.next-btn-primary:has-text("确认")'
        ).first
        if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
            await confirm_btn.click()
            await asyncio.sleep(1.5)
    except Exception:
        pass
```

3. **替换 `_link_products_or_shops` 方法**(platform.py:1372-1528)。新签名 `(frame, link_type, items)`,不再 `(frame, link_type, names)`:

```python
    @staticmethod
    async def _link_products_or_shops(frame, link_type: str, items: list) -> None:
        """发布时关联商品/店铺(按 trace 分组重现 + itemId 定位)。

        Args:
            frame: 发布页 iframe
            link_type: 'product' / 'shop'
            items: [{title?, image?, id?, trace?}, ...] — 兼容旧格式
        """
        if not items:
            return
        await _replay_groups(frame, link_type, items, max_load_more=5)
```

4. **修改 `_upload_single_video` 调用**(platform.py:531-532):

```python
                # 8.5 关联商品/店铺(可选,最多 6 个)
                if link_type in ("product", "shop") and link_items:
                    await self._link_products_or_shops(frame, link_type, link_items)
```

5. **修改 `_upload_single_video` 签名**(platform.py:456-468),`link_names: list` → `link_items: list`:

```python
    async def _upload_single_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        desc: str = "",
        claim: str = "",
        thumbnail_path: str | None = None,
        link_type: str = "",
        link_items: list = None,
    ) -> None:
```

并在 `_upload_single_video` 函数体内将 `link_names` 全部替换为 `link_items`(grep 检查):

```bash
cd backend && grep -n "link_names" impl/taobao_guanghe/platform.py
```

应为空(全改完)。

6. **修改 `publish_video` 读取字段**(platform.py:370-378):

```python
            # 关联商品/店铺('product'/'shop',空字符串=不关联)
            link_type = (kwargs.get("guangheLinkType", "") or "").strip()
            # 完整对象列表(每项含 title/id/trace);旧数据可能只有 title 或仅为字符串
            if link_type == "product":
                raw = kwargs.get("guangheProducts", []) or []
            elif link_type == "shop":
                raw = kwargs.get("guangheShops", []) or []
            else:
                raw = []
            # 规范化:字符串 → {title: s};dict 直接用
            link_items = []
            for it in raw[:6]:
                if isinstance(it, str):
                    link_items.append({"title": it})
                elif isinstance(it, dict):
                    link_items.append(it)
```

并将调用 `_upload_single_video` 处的 `link_names=link_names` 改为 `link_items=link_items`:

```python
                        await self._upload_single_video(
                            title=title,
                            file_path=file_path,
                            tags=tags,
                            publish_date=publish_date,
                            account_file=cookie_path,
                            desc=desc,
                            claim=claim,
                            thumbnail_path=picked_thumb,
                            link_type=link_type,
                            link_items=link_items,
                        )
```

同时删除原 platform.py:373-378 那段 `if link_type == "product": link_names = ...` 旧逻辑。

- [ ] **Step 4.4: 跑测试看通过**

```bash
cd backend && python -m pytest tests/test_guanghe_link_group_replay.py tests/test_guanghe_trace_signature.py tests/test_guanghe_link_ops_locate.py -v
```

Expected: PASS(all)

- [ ] **Step 4.5: Commit**

```bash
git add backend/impl/taobao_guanghe/platform.py backend/tests/test_guanghe_link_group_replay.py
git commit -m "feat(taobao_guanghe): _link_products_or_shops 按 trace 分组重现 + 中断策略"
```

---

## Task 5: app.py 4 处字段名改造(含兼容)

**Files:**
- Modify: `backend/app.py:1063-1066, 1158-1161, 1250-1253, 1289-1292`

- [ ] **Step 5.1: 找出所有 guangheProductNames/guangheShopNames 出现位置**

```bash
cd backend && grep -n "guangheProductNames\|guangheShopNames" app.py
```

应输出 8 行(4 处 × 2 字段)。每处把:

```python
                guangheProductNames=data.get('guangheProductNames', []),
                guangheShopNames=data.get('guangheShopNames', []),
```

替换为:

```python
                guangheProducts=data.get('guangheProducts') or data.get('guangheProductNames') or [],
                guangheShops=data.get('guangheShops') or data.get('guangheShopNames') or [],
```

兼容逻辑:优先读新字段 `guangheProducts`,缺失时回退到旧字段 `guangheProductNames`。这样老前端不升级也能继续工作。

- [ ] **Step 5.2: 启动后端验证无报错**

```bash
cd backend && python app.py
```

Expected: 启动成功,日志显示 `Serving on http://0.0.0.0:5409`。

- [ ] **Step 5.3: Commit**

```bash
git add backend/app.py
git commit -m "feat(taobao_guanghe): app.py 透传 guangheProducts/guangheShops 完整对象(兼容旧字段名)"
```

---

## Task 6: GuangheItemPicker.vue trace 快照

**Files:**
- Modify: `frontend/src/components/GuangheItemPicker.vue`

- [ ] **Step 6.1: selectedNames → selectedItems(含 id/trace)**

Edit `frontend/src/components/GuangheItemPicker.vue`:

1. **添加 activeTab ref**(line 153 附近,在 `const activeRule = ref('')` 之前加):

```javascript
const activeTab = ref('preferred') // 商品模式默认 preferred,店铺模式固定 'shop'
```

2. **重命名 selectedNames → selectedItems**(全局替换,但要逐处确认):

```bash
cd frontend && grep -n "selectedNames" src/components/GuangheItemPicker.vue
```

将所有 `selectedNames` 改为 `selectedItems`。

3. **onCardClick 改为打包 trace 快照**(原 line 309-321):

```javascript
function onCardClick(item) {
  if (item.disabled) return
  if (isSelected(item)) {
    selectedItems.value = selectedItems.value.filter(s => s.id !== item.id && s.title !== item.title)
  } else {
    if (selectedItems.value.length >= MAX_SELECTED) {
      ElMessage.warning(`最多选择 ${MAX_SELECTED} 个`)
      return
    }
    // 打包 trace 快照(选中那一刻的面板状态)
    const trace = {
      tab: props.mode === 'shop' ? 'shop' : activeTab.value,
      keyword: searchKeyword.value || '',
      rule: props.mode === 'shop' ? '' : (activeRule.value || ''),
      category: props.mode === 'shop' ? '' : (activeCategory.value || ''),
    }
    selectedItems.value = [...selectedItems.value, {
      title: item.title,
      image: item.image || '',
      id: item.id || item.title,  // 商品用 itemId,店铺兜底 title
      trace,
    }]
  }
}
```

4. **isSelected 兼容 id + title**(原 line 305-307):

```javascript
function isSelected(item) {
  return selectedItems.value.some(s =>
    (s.id && s.id === item.id) || s.title === item.title
  )
}
```

5. **removeSelected 改为按 id/title 双重匹配**(原 line 323-325):

```javascript
function removeSelected(item) {
  // item 现在是完整对象({title, image, id, trace}),不是裸字符串
  const key = typeof item === 'string' ? item : (item.id || item.title)
  selectedItems.value = selectedItems.value.filter(s =>
    (s.id !== key) && (s.title !== key)
  )
}
```

6. **normalizeSelected 升级,透传 trace**(原 line 293-303):

```javascript
function normalizeSelected(arr) {
  if (!Array.isArray(arr)) return []
  return arr
    .map(item => {
      if (typeof item === 'string') return { title: item, image: '', id: item, trace: undefined }
      return {
        title: item.title || '',
        image: item.image || '',
        id: item.id || item.title || '',
        trace: item.trace,  // 旧数据可能 undefined
      }
    })
    .filter(it => it.title || it.id)
    .slice(0, MAX_SELECTED)
}
```

7. **onConfirm emit 完整对象数组**(原 line 327-330):

```javascript
function onConfirm() {
  emit('confirm', [...selectedItems.value])
  emit('update:modelValue', false)
}
```

8. **openPanel 重置 activeTab**(原 line 205-234,在 `loading.value = true` 之前加):

```javascript
async function openPanel() {
  // ... 原有 accountId 校验 ...
  selectedItems.value = normalizeSelected(props.initSelected)
  rules.value = []
  categories.value = []
  activeRule.value = ''
  activeCategory.value = ''
  activeTab.value = props.mode === 'shop' ? 'shop' : 'preferred'  // 新增
  searchKeyword.value = ''
  // ... 后续逻辑不变 ...
}
```

9. **mode watch 重置 activeTab**(原 line 182-203,加 activeTab 重置):

```javascript
watch(() => props.mode, async (newMode, oldMode) => {
  if (!props.modelValue || newMode === oldMode || !sessionId.value) return
  loading.value = true
  try {
    const res = await guangheApi.pickerSwitchType(sessionId.value, newMode)
    items.value = res.data?.items || []
    hasMore.value = !!res.data?.has_more
    if (newMode === 'product') {
      applyFilters(res.data?.filters)
    } else {
      rules.value = []
      categories.value = []
    }
    activeRule.value = ''
    activeCategory.value = ''
    activeTab.value = newMode === 'shop' ? 'shop' : 'preferred'  // 新增
    searchKeyword.value = ''
  } catch (e) {
    ElMessage.error('切换类型失败: ' + (e?.message || e))
  } finally {
    loading.value = false
  }
})
```

10. **template 中「已选 N/6」chip 渲染**(原 line 105-112)适配新结构:

```vue
<el-tag
  v-for="(item, i) in selectedItems"
  :key="i + '_' + (item.id || item.title)"
  size="small"
  closable
  @close="removeSelected(item)"
>{{ item.title }}</el-tag>
```

注意:`@close` 之前传 `item.title`(字符串),现在传完整 `item` 对象。

- [ ] **Step 6.2: 前端 dev 验证**

```bash
cd frontend && npm run dev
```

打开浏览器 → 淘宝光合选品弹窗 → 选 3 个商品(做不同的搜索/筛选)→ 用 Vue DevTools 查看 `selectedItems` 结构应含 `{title, image, id, trace}`。

- [ ] **Step 6.3: Commit**

```bash
git add frontend/src/components/GuangheItemPicker.vue
git commit -m "feat(taobao_guanghe): picker 卡片选中时打包 trace 快照"
```

---

## Task 7: PublishCenter.vue 提交字段升级

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue:1092, 2736-2742`

- [ ] **Step 7.1: 修改提交 publish 时的字段名**

Edit `frontend/src/views/PublishCenter.vue`,定位 line 2736-2742,把:

```javascript
        guangheLinkType: merged.guangheLinkType || '',
        guangheProductNames: (merged.guangheProducts || [])
          .map(p => (typeof p === 'string' ? p : p?.title).trim())
          .filter(Boolean),
        guangheShopNames: (merged.guangheShops || [])
          .map(s => (typeof s === 'string' ? s : s?.title).trim())
          .filter(Boolean),
```

替换为:

```javascript
        guangheLinkType: merged.guangheLinkType || '',
        // 完整透传含 id 和 trace 的对象数组,后端按 trace 分组重现
        // 兼容旧字符串:统一规整为 {title, image, id, trace}
        guangheProducts: (merged.guangheProducts || [])
          .map(p => typeof p === 'string'
            ? { title: p, image: '', id: p, trace: undefined }
            : {
                title: p?.title || '',
                image: p?.image || '',
                id: p?.id || p?.title || '',
                trace: p?.trace,
              })
          .filter(p => p.title || p.id),
        guangheShops: (merged.guangheShops || [])
          .map(s => typeof s === 'string'
            ? { title: s, image: '', id: s, trace: undefined }
            : {
                title: s?.title || '',
                image: s?.image || '',
                id: s?.id || s?.title || '',
                trace: s?.trace,
              })
          .filter(s => s.title || s.id),
```

- [ ] **Step 7.2: 验证 form 默认值(line 1092)**

确认 line 1092 附近 `taobao_guanghe: { ..., guangheProducts: [], guangheShops: [], ... }` 已存在(应无需改动,只是数组里元素结构升级)。

```bash
cd frontend && grep -n "guangheProducts: \[\]" src/views/PublishCenter.vue
```

应能命中。

- [ ] **Step 7.3: 验证 saveDraft/loadDraft 不需改动**

确认 `form.guangheProducts` 通过 draft_data JSON 自动持久化(无需特殊处理):

```bash
cd frontend && grep -n "guangheProducts\|guangheShops" src/views/PublishCenter.vue
```

应只在 form 初始化、currentGuangheItems computed、onGuanghePickerConfirm 等处出现,不涉及 saveDraft/loadDraft 的特殊处理(因为它们序列化的是整个 form 对象)。

- [ ] **Step 7.4: 前端构建验证**

```bash
cd frontend && npm run build
```

Expected: 构建无报错。

- [ ] **Step 7.5: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(taobao_guanghe): PublishCenter 提交完整对象数组(含 id/trace)"
```

---

## Task 8: 联调验收

**Files:** 无(纯验证)

- [ ] **Step 8.1: 启动前后端**

```bash
# Terminal 1
cd backend && python app.py
# Terminal 2
cd frontend && npm run dev
```

- [ ] **Step 8.2: 选品轨迹验证**

1. 打开淘宝光合选品弹窗(关联商品模式)
2. 搜「小米17」→ 选商品 A
3. 不动筛选,继续选商品 B
4. 清空搜索 → 选商品 C
5. 点确认
6. 打开浏览器 DevTools → Network → 查看 POST /api/publish 的 payload:

```
guangheProducts[0].trace.keyword === '小米17'
guangheProducts[1].trace.keyword === '小米17'  // A、B 共享
guangheProducts[2].trace.keyword === ''        // C 没搜
```

- [ ] **Step 8.3: 发布可靠性**

1. 完整发布一条淘宝光合视频(关联商品按 Step 8.2 设置)
2. 后端日志应显示:
   - `[关联商品] 共 3 个,2 组轨迹`
   - `组 1/2: tab=preferred kw='小米17' rule='' category='' → 2 个目标`
   - `组 1/2 ✓ 勾选完成 (尝试 1 次)`
   - `组 2/2: tab=preferred kw='' rule='' category='' → 1 个目标`
3. `logs/guanghe_before_submit.png` 截图中面板里 3 个商品都应勾上

- [ ] **Step 8.4: 中断策略**

1. 手动改坏 draft_data JSON,把某 trace.keyword 改成「___不可能搜到的词___」
2. 重新加载草稿,点发布
3. 后端应 raise:`RuntimeError: 未找到的商品 id(超过 5 次加载更多): ['xxx']`
4. 前端发布失败提示应包含具体 id

- [ ] **Step 8.5: 草稿持久化**

1. 设置好关联商品后点「保存草稿」
2. 刷新浏览器
3. 草稿箱加载该草稿 → form.guangheProducts 应含完整 trace
4. Vue DevTools 验证 trace 字段无丢失

- [ ] **Step 8.6: 店铺模式回归**

1. 切到关联店铺模式
2. 选 2 个店铺(一个用搜索、一个不搜索)
3. 验证 trace.tab === 'shop'、rule === ''、category === ''
4. 发布,后端日志显示「组」分组正确,勾选成功

- [ ] **Step 8.7: 旧数据兼容**

1. 找一个旧版本(改造前)保存的草稿(`guangheProducts: [{title, image}]` 无 id/trace)
2. 加载并发布
3. 后端日志应显示 `[关联商品] 检测到旧格式数据,退回 title 匹配路径`
4. 走旧路径尝试匹配;找不到时按"中断发布"处理

---

## 自检清单(写完后自查)

- [x] **Spec 覆盖**:
  - §4 架构改动 → Task 1-7
  - §5 数据结构 → Task 1(trace_signature) + Task 6(前端 trace 快照)
  - §6 数据流 → Task 4(_replay_groups) + Task 6/7(前端选品/提交)
  - §7 错误处理 → Task 4(`disabled`/`missing`/`raise`)+ Task 4(旧路径 `_legacy_link_by_title`)
  - §8 测试 → Task 1/3/4 单测 + Task 8 手动冒烟
  - §9 实施顺序 → Task 1-2(Step 1)+ Task 3-4(Step 2)+ Task 6(Step 3)+ Task 7(Step 4)+ Task 8(Step 5)
  - §10 验收 → Task 8

- [x] **占位符**:无 TBD/TODO/"实现细节后补"等

- [x] **类型一致性**:
  - `trace_signature` 在 Task 1 定义,Task 4 `_group_by_trace` 调用 ✓
  - `locate_and_check` 在 Task 3 定义,Task 4 `_replay_groups` 调用 ✓
  - `_link_ops.scrape/switch_radio/click_add_card/...` 在 Task 2 定义,Task 4 调用 ✓
  - 前端 `selectedItems` 元素结构 `{title, image, id, trace}` 在 Task 6/7/后端 Task 4 一致 ✓
  - 字段名 `guangheProducts`/`guangheShops` 在 Task 5(后端透传) + Task 4(platform 读取) + Task 7(前端提交) 三处一致 ✓
