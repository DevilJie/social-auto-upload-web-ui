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
    """点「加载更多」,返回是否实际点击(无按钮时尝试滚动触发懒加载,返回 False)。

    行为:
    - 有「加载更多」按钮 → 点击,返回 True
    - 无按钮 → 滚动激活的 tabpanel + body 到底(触发无限滚动懒加载),返回 False
    """
    more_btn = frame.get_by_text("加载更多", exact=True).first
    if await more_btn.count() > 0:
        try:
            await more_btn.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        await more_btn.click()
        await asyncio.sleep(2)
        return True
    # 兜底:滚动激活的 tabpanel + body 触发懒加载
    try:
        await frame.evaluate(
            """() => {
                const p = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                if (p) { p.scrollTop = p.scrollHeight; }
                window.scrollTo(0, document.body.scrollHeight);
            }"""
        )
        await asyncio.sleep(2)
    except Exception:
        pass
    return False
