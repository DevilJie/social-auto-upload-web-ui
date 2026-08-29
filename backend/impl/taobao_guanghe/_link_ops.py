"""淘宝光合「关联商品/店铺」DOM 操作工具函数(纯函数,参数为 frame)。

picker.py 和 platform.py 共用同一份 DOM 操作代码,保证选品/发布两条路径行为一致。

设计原则:
- 所有函数都接受 frame 作为第一个参数(发布页 iframe 或主 frame)
- 不持有任何会话状态,纯 DOM 操作
- 失败时抛异常或返回空,由调用方决定如何处理
"""

from __future__ import annotations

import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("taobao_guanghe")

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

async def ensure_link_section_ready(frame, type_: str, timeout_s: int = 15) -> None:
    """确保发布页「关联商品/店铺」区域已渲染(发布路径专用)。

    背景: picker 是一进发布页就开面板,所以关联商品区立即可见。
    发布路径会先上传视频/封面/标题/描述/创作者声明,这些操作可能
    让关联商品区延迟渲染,导致 switch_radio/click_add_card 直接
    wait_for 超时 10s 然后 raise TimeoutError(实际用户体感:11 秒后
    「浏览器已关闭」)。

    修复: 显式滚动到页面底部 + 等待「关联商品/店铺」表单区出现,
    再交给 switch_radio/click_add_card。

    DOM 锚点: ``form-item:has-text("关联商品")`` / ``form-item:has-text("关联店铺")``
    (光合发布页关联商品是一个独立的 form-item 区块)。
    """
    section_text = "关联商品" if type_ == TYPE_PRODUCT else "关联店铺"
    # 诊断 1: 当前 frame 的 URL(确认是不是 huodong 发布表单 frame)
    try:
        logger.info("[关联%s][诊断] 当前 frame.url=%s", section_text, frame.url or "(空)")
    except Exception:
        pass
    # 诊断 2: 当前 frame 里所有 .next-radio-label 文本
    try:
        labels = await frame.locator(".next-radio-label").all_text_contents()
        logger.info(
            "[关联%s][诊断] 当前 frame radio-labels: %s",
            section_text,
            [t.strip()[:30] for t in (labels or [])],
        )
    except Exception:
        pass
    # 诊断 3: 当前 frame body 里含「商品/店铺/关联/添加」的文本片段
    #         (确认关联商品入口到底叫什么、长什么样)
    try:
        snippets = await frame.evaluate(
            """() => {
                const text = (document.body && document.body.innerText) || '';
                const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
                const kw = ['商品', '店铺', '关联', '添加', '带货', '选品'];
                return lines.filter(l => kw.some(k => l.includes(k))).slice(0, 30);
            }"""
        )
        logger.info("[关联%s][诊断] 含关键词文本片段: %s", section_text, snippets)
    except Exception:
        pass
    # 诊断 4: 页面所有 frame 的 URL(看关联商品区是否在另一个 iframe)
    try:
        page = frame.page
        urls = [f.url for f in (page.frames if page else [])]
        logger.info("[关联%s][诊断] 全部 frames(%d): %s", section_text, len(urls), urls)
    except Exception:
        pass
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            # 1) 滚动 frame 内容到底部,触发懒加载区域
            await frame.evaluate(
                "() => { const c = document.querySelector('.post-side, .form-area, body');"
                "  if (c) c.scrollTop = c.scrollHeight || 99999;"
                "  window.scrollTo(0, document.body.scrollHeight); }"
            )
            # 2) 等关联商品 form-item 出现
            section = frame.locator(f'.form-item:has-text("{section_text}")').first
            if await section.count() > 0 and await section.is_visible():
                # 滚到 section 视口内
                try:
                    await section.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                return
        except Exception:
            pass
        await asyncio.sleep(0.8)
    # 超时不 raise —— 让后续 switch_radio/wait_panel_ready 仍有机会命中
    # (避免遮蔽其它可能更准的错误信息)


async def switch_radio(frame, type_: str) -> None:
    """切换商品/店铺 radio(.next-radio-label + 文本)。"""
    target_label = "商品" if type_ == TYPE_PRODUCT else "店铺"
    radio_label = frame.locator(f'.next-radio-label:has-text("{target_label}")').first
    try:
        await radio_label.wait_for(state="visible", timeout=10000)
    except Exception as exc:
        raise RuntimeError(
            f"switch_radio 找不到可见 radio(文本={target_label}): {exc}"
        ) from exc
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
    try:
        await trigger.wait_for(state="visible", timeout=8000)
    except Exception as exc:
        raise RuntimeError(
            f"click_add_card 找不到可见触发器(文本={trigger_text}): {exc}"
        ) from exc
    await trigger.click()
    await asyncio.sleep(2)


async def wait_panel_ready(frame, type_: str) -> None:
    """等待选择面板就绪(商品:等 tab;店铺:等搜索框)。"""
    if type_ == TYPE_PRODUCT:
        try:
            await frame.locator(
                '.next-tabs-tab:has-text("已购商品"), .next-tabs-tab:has-text("平台优选")'
            ).first.wait_for(state="visible", timeout=10000)
        except Exception as exc:
            raise RuntimeError(
                "wait_panel_ready(商品) 等不到「已购商品/平台优选」tab: %s" % exc
            ) from exc
    else:
        try:
            await frame.locator('input[placeholder*="店铺"]').first.wait_for(
                state="visible", timeout=10000
            )
        except Exception as exc:
            raise RuntimeError(
                "wait_panel_ready(店铺) 等不到店铺搜索框: %s" % exc
            ) from exc


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
