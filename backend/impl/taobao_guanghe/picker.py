"""淘宝光合「关联商品/店铺」选择面板 —— 浏览器会话池。

用户在前端弹窗操作时,后端同步驱动一个常驻无头浏览器:
进入光合首页 → 进入视频发布页 → 切换商品/店铺 radio → 点添加卡片 → 弹出选择面板。
搜索/筛选/加载更多等操作都在该浏览器内同步执行,然后抓取 DOM 数据回传前端。

生命周期:
- 前端打开弹窗 → ``open`` 创建会话并初始化到选择面板
- 用户操作 → ``switch_type``/``switch_tab``/``apply_filter``/``search``/``load_more``
- 前端关闭弹窗 → ``close`` 释放浏览器

DOM 选择器策略(避免 CSS Modules 哈希 class 模糊匹配):
- Next UI 稳定 class: ``.next-tabs-tab`` / ``.next-checkbox-wrapper`` / ``.next-radio-wrapper`` / ``.next-icon-plus`` / ``.next-btn-primary``
- ARIA 属性: ``role="tabpanel"[aria-hidden="false"]`` / ``input[role="searchbox"]``
- 稳定属性: ``href*="item.taobao.com"`` / ``span[title]`` / ``placeholder*="店铺"``
- 文本锚点: ``get_by_text("添加商品", exact=True)`` / ``get_by_text("加载更多")``
- 复杂关系(卡片定位) 用 ``frame.evaluate(JS)`` 以稳定锚点向上找祖先
"""

import asyncio
import sqlite3
import threading
import urllib.parse
from pathlib import Path

from conf import BASE_DIR
from util._logger import get_channel_logger

from .._browser import create_browser, create_context

logger = get_channel_logger("taobao_guanghe")

_GUANGHE_HOME_URL = "https://creator.guanghe.taobao.com/"
_COOKIE_INVALID_MARKERS = ("login.taobao.com",)

# radio 文案
_TYPE_PRODUCT = "商品"
_TYPE_SHOP = "店铺"

# 视频发布页 URL(发布页内容由 pub_url 指向的跨域 iframe 嵌入)
# 直接 goto 此 URL,跳过 hover 菜单导航,流程更稳定
_GUANGHE_PUBLISH_URL = (
    "https://creator.guanghe.taobao.com/page/pubNew/video"
    "?pub_url=https%3A%2F%2Fhuodong.taobao.com%2Fwow%2Fz%2Fguang%2Fgg_publish%2Fgg-video"
    "%3Fugc_scene%3Dpc_newcreator_video%26pageType%3Dvideo%26site%3Dguangguang"
    "&pub_scene=gg"
)


# ----------------------------------------------------------------------
# Cookie 路径解析
# ----------------------------------------------------------------------

def _get_cookie_path_by_account_id(account_id: str) -> str | None:
    """根据 user_info.id 取 cookiesFile 路径。"""
    if not account_id:
        return None
    db_path = str(Path(BASE_DIR / "db" / "database.db"))
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _resolve_cookie_path(cookie_filename: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile") / cookie_filename)


# ----------------------------------------------------------------------
# 单个会话
# ----------------------------------------------------------------------

class GuanghePickerSession:
    """一个账号 + 一个常驻无头浏览器,负责 picker 全流程操作。"""

    def __init__(self, session_id: str, cookie_path: str):
        self.session_id = session_id
        self.cookie_path = cookie_path
        self.browser = None
        self.context = None
        self.page = None
        self.frame = None  # 发布页 iframe
        self.current_type: str | None = None  # 'product' / 'shop'

    # ---- 生命周期 ----

    async def open(self, type_: str) -> dict:
        """启动浏览器并初始化到选择面板。

        Args:
            type_: 'product' 或 'shop'

        Returns:
            ``{"items": [...], "has_more": bool, "type": ...}``
        """
        if type_ not in ("product", "shop"):
            raise ValueError(f"unknown type: {type_}")

        logger.info(f"[Picker][{self.session_id}] open type={type_}")
        self.browser = await create_browser(headless=False)
        try:
            self.context = await create_context(self.browser, storage_state=self.cookie_path)
            self.page = await self.context.new_page()

            # 直接带 cookie goto 发布页 URL(跳过先访问首页)
            # 失效 cookie 会被淘宝重定向到 login.taobao.com,据此判断登录状态
            logger.info(f"[Picker] goto 发布页: {_GUANGHE_PUBLISH_URL[:80]}...")
            await self.page.goto(_GUANGHE_PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            current_url = self.page.url or ""
            if any(m in current_url for m in _COOKIE_INVALID_MARKERS):
                raise RuntimeError("cookie 失效,请重新登录淘宝光合")

            # 找到发布页 iframe
            self.frame = await self._find_publish_frame()

            # 提前设置 current_type,让 _open_picker_panel 内部能调 switch_tab
            # (switch_tab 会校验 self.current_type,提前设置才能正确切换到「平台优选」)
            self.current_type = type_

            # 点对应 radio + 点添加卡片,打开选择弹窗
            await self._open_picker_panel(type_)

            # 抓取初始数据 + 筛选选项
            items, has_more = await self._scrape()
            filters = await self._scrape_filters() if type_ == "product" else {}
            return {"items": items, "has_more": has_more, "filters": filters, "type": type_}
        except Exception:
            # 初始化失败立即释放浏览器
            await self._teardown()
            raise

    async def switch_type(self, type_: str) -> dict:
        """切换商品↔店铺(关闭当前选择面板 → 切 radio → 重开面板)。"""
        if type_ not in ("product", "shop"):
            raise ValueError(f"unknown type: {type_}")
        if type_ == self.current_type:
            # 已是该类型,直接返回当前快照
            items, has_more = await self._scrape()
            return {"items": items, "has_more": has_more, "type": type_}

        logger.info(f"[Picker][{self.session_id}] switch {self.current_type}→{type_}")
        # 关闭当前弹窗(Esc)
        try:
            await self.frame.page.keyboard.press("Escape")
            await asyncio.sleep(0.8)
        except Exception:
            pass

        await self._open_picker_panel(type_)
        self.current_type = type_

        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more, "type": type_}

    async def switch_tab(self, tab: str) -> dict:
        """商品模式:切换「已购商品」/「平台优选」。

        增加切换验证:点击后等待目标 tab 变成 active,避免点击失效时抓错 panel 数据。
        """
        if self.current_type != "product":
            raise RuntimeError("tab 切换仅商品模式支持")
        if tab not in ("bought", "preferred"):
            raise ValueError(f"unknown tab: {tab}")

        target_text = "已购商品" if tab == "bought" else "平台优选"
        logger.info(f"[Picker][{self.session_id}] switch_tab → {target_text}")
        try:
            tab_el = self.frame.locator(
                f'.next-tabs-tab:has-text("{target_text}")'
            ).first
            await tab_el.wait_for(state="visible", timeout=5000)

            is_active = await tab_el.evaluate("el => el.classList.contains('active')")
            if not is_active:
                await tab_el.click()
                # 等目标 tab 变为 active(点击成功 + React 重渲染完成)
                try:
                    await self.frame.wait_for_function(
                        """(text) => {
                            const tabs = document.querySelectorAll('.next-tabs-tab');
                            return [...tabs].some(t =>
                                (t.textContent || '').includes(text) && t.classList.contains('active')
                            );
                        }""",
                        target_text,
                        timeout=5000,
                    )
                    logger.info(f"[Picker] ✓ tab 已切换并验证为 active: {target_text}")
                except Exception as e:
                    logger.info(f"[Picker] tab 切换验证超时(可能未生效): {e}")
                # 等 panel 内容刷新
                await asyncio.sleep(1.2)
            else:
                logger.info(f"[Picker] tab 已是 active,无需切换: {target_text}")
        except Exception as e:
            logger.info(f"[Picker] switch_tab 失败: {e}")

        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more}

    async def apply_filter(self, rule: str | None = None, category: str | None = None) -> dict:
        """切换推荐规则/品类筛选(仅平台优选 tab 有效)。

        Args:
            rule: 推荐规则(如"全部"/"主推品"/"新品"——具体选项由面板 DOM 决定)
            category: 品类(如"全部"/"穿搭"/...——具体选项由面板 DOM 决定)

        Returns:
            ``{"items": [...], "has_more": bool, "filters": {"rules": [...], "categories": [...]}}``
            返回最新筛选选项,前端据此动态渲染。
        """
        if self.current_type != "product":
            raise RuntimeError("筛选仅商品模式支持")

        if rule:
            await self._click_filter_option("推荐规则", rule)
        if category:
            await self._click_filter_option("品类筛选", category)

        await asyncio.sleep(1.2)
        items, has_more = await self._scrape()
        filters = await self._scrape_filters()
        return {"items": items, "has_more": has_more, "filters": filters}

    async def search(self, keyword: str) -> dict:
        """搜索。

        关键:必须限定在激活的 ``[role="tabpanel"][aria-hidden="false"]`` 内找 input,
        因为隐藏 tab("已购商品")里也有同款 searchbox,``.first`` 会取到隐藏的那个。
        """
        keyword = (keyword or "").strip()
        logger.info(f"[Picker][{self.session_id}] search: {keyword!r}")
        try:
            panel = self.frame.locator('[role="tabpanel"][aria-hidden="false"]')
            inp = panel.locator('input[role="searchbox"]').first
            await inp.wait_for(state="visible", timeout=5000)
            await inp.click()
            await inp.fill("")
            if keyword:
                await inp.fill(keyword)
            await asyncio.sleep(0.3)
            await inp.press("Enter")
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.info(f"[Picker] search 失败: {e}")

        items, has_more = await self._scrape()
        filters = await self._scrape_filters() if self.current_type == "product" else {}
        return {"items": items, "has_more": has_more, "filters": filters}

    async def load_more(self) -> dict:
        """点击「加载更多」按钮(用文本定位,只有在还有更多时才出现)。"""
        logger.info(f"[Picker][{self.session_id}] load_more")
        try:
            # "加载更多"文本唯一,只在加载更多按钮上出现
            more_btn = self.frame.get_by_text("加载更多", exact=True).first
            if await more_btn.count() > 0:
                try:
                    await more_btn.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
                await more_btn.click()
                await asyncio.sleep(2)
            else:
                # 兜底:滚动当前激活的 tabpanel 触发懒加载
                await self.frame.evaluate(
                    """() => {
                        const p = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                        if (p) { p.scrollTop = p.scrollHeight; }
                        // 退一步:滚动整个 body
                        window.scrollTo(0, document.body.scrollHeight);
                    }"""
                )
                await asyncio.sleep(2)
        except Exception as e:
            logger.info(f"[Picker] load_more 失败: {e}")

        items, has_more = await self._scrape()
        return {"items": items, "has_more": has_more}

    async def close(self) -> None:
        """关闭浏览器,释放所有资源。"""
        logger.info(f"[Picker][{self.session_id}] close")
        await self._teardown()

    # ---- 内部辅助 ----

    async def _find_publish_frame(self):
        """找含上传元素的 iframe(发布页内容由跨域 iframe 嵌入)。"""
        page = self.page
        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    # 发布页 iframe 内会有 file input(上传视频用);用它判定 iframe 已就绪
                    inp_count = await frame.locator(
                        'input[type="file"]'
                    ).count()
                    if inp_count > 0:
                        return frame
                except Exception:
                    pass
            await asyncio.sleep(1)
        return page.main_frame

    async def _open_picker_panel(self, type_: str) -> None:
        """在发布页 iframe 内:点对应 radio → 点添加卡片 → 等选择面板出现。

        - 商品/店铺切换 radio: Next UI ``.next-radio-label`` + 文本(商品/店铺)
        - 添加卡片: 用文本"添加商品"/"添加店铺"精确定位
          (切换 radio 后只有对应类型的添加卡可见,不会误中)
        - 面板就绪: 商品模式见 ``.next-tabs-tab``,店铺模式见 placeholder 含"店铺"的搜索框
        """
        frame = self.frame
        target_label = _TYPE_PRODUCT if type_ == "product" else _TYPE_SHOP
        trigger_text = "添加商品" if type_ == "product" else "添加店铺"

        # 1. 点对应 radio(.next-radio-label 是 Next UI 稳定 class)
        try:
            radio_label = frame.locator(
                f'.next-radio-label:has-text("{target_label}")'
            ).first
            await radio_label.wait_for(state="visible", timeout=10000)
            is_checked = await radio_label.evaluate(
                "el => el.closest('label')?.classList.contains('checked')"
            )
            if not is_checked:
                await radio_label.click()
                await asyncio.sleep(0.8)
            logger.info(f"[Picker] ✓ 已选 radio={target_label}")
        except Exception as e:
            logger.info(f"[Picker] radio 点击失败: {e}")

        # 2. 点添加卡片(用文本精确匹配;切换 radio 后只有一个添加卡可见)
        try:
            trigger = frame.get_by_text(trigger_text, exact=True).first
            await trigger.wait_for(state="visible", timeout=8000)
            await trigger.click()
            logger.info(f"[Picker] ✓ 已点击 {trigger_text}")
            await asyncio.sleep(2)
        except Exception as e:
            logger.info(f"[Picker] 添加卡片点击失败: {e}")

        # 3. 等待弹窗内的核心元素出现(标识面板已展开)
        try:
            if type_ == "product":
                # 商品模式:等 tabs(已购商品/平台优选)
                await frame.locator(
                    '.next-tabs-tab:has-text("已购商品"), .next-tabs-tab:has-text("平台优选")'
                ).first.wait_for(state="visible", timeout=10000)
                # 默认进入「平台优选」(用户要求)
                await self.switch_tab("preferred")
            else:
                # 店铺模式:等搜索框
                await frame.locator('input[placeholder*="店铺"]').first.wait_for(
                    state="visible", timeout=10000
                )
        except Exception as e:
            logger.info(f"[Picker] 面板等待失败: {e}")

    async def _click_filter_option(self, row_label: str, option_text: str) -> None:
        """点击筛选选项(基于行标签文本"推荐规则:"/"品类筛选:"定位)。

        关键修复:
        - label 用 substring 匹配(``get_by_text(text, exact=False)``),因为 DOM 文本是
          "推荐规则："（带冒号）,传"推荐规则"用 exact=True 找不到
        - 必须限定在激活的 ``[role="tabpanel"][aria-hidden="false"]`` 内,避免匹配到
          隐藏 tab 内的同名文本
        - 选项点击 + 状态检测走 JS evaluate(避开 CSS Modules class)
        """
        try:
            panel = self.frame.locator('[role="tabpanel"][aria-hidden="false"]')
            # substring 匹配: "推荐规则" 能匹配 "推荐规则："
            label_el = panel.get_by_text(row_label, exact=False).first
            if await label_el.count() == 0:
                logger.info(f"[Picker] 筛选行标签未找到: {row_label}")
                return

            result = await label_el.evaluate(
                """(el, optText) => {
                    // 向上找含选项的行容器
                    let row = el.parentElement;
                    for (let i = 0; i < 5 && row; i++) {
                        const all = row.querySelectorAll('*');
                        for (const o of all) {
                            if (o === el) continue;
                            if (o.children.length > 0) continue;  // 叶节点
                            const t = (o.textContent || '').trim();
                            if (t === optText) {
                                const classes = [...o.classList, ...(o.parentElement?.classList || [])];
                                const isActive = classes.some(c => c === 'active' || c.endsWith('-active--'));
                                if (isActive) return 'active';
                                o.click();
                                return 'clicked';
                            }
                        }
                        row = row.parentElement;
                    }
                    return 'not_found';
                }""",
                option_text,
            )
            if result == 'clicked':
                logger.info(f"[Picker] ✓ 筛选 {row_label} → {option_text}")
            elif result == 'active':
                logger.info(f"[Picker] 筛选已激活 {row_label} → {option_text}")
            else:
                logger.info(f"[Picker] 筛选选项未找到 {row_label} → {option_text}")
        except Exception as e:
            logger.info(f"[Picker] 筛选点击失败(row={row_label}, opt={option_text}): {e}")

    async def _scrape_filters(self) -> dict:
        """抓取当前激活 tabpanel 的推荐规则/品类筛选选项。

        策略:
        - 找文本以 "推荐规则" / "品类筛选" 开头的叶节点(label)
        - label 的下一个兄弟元素就是选项容器(filter-group)
        - 收集 filter-group 内的叶节点文本作为选项列表

        Returns:
            ``{"rules": [...], "categories": [...]}`` 抓不到时为空数组
        """
        try:
            data = await self.frame.evaluate(
                """() => {
                    const out = {rules: [], categories: []};
                    const panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                    if (!panel) return out;

                    function getOptions(labelPrefix) {
                        // 找文本以 labelPrefix 开头的叶节点
                        const leaves = Array.from(panel.querySelectorAll('*')).filter(el => {
                            if (el.children.length > 0) return false;
                            const t = (el.textContent || '').trim();
                            return t.startsWith(labelPrefix);
                        });
                        if (!leaves.length) return [];
                        const label = leaves[0];
                        // 选项容器:label 的下一个兄弟(filter-group);兜底用父级
                        let group = label.nextElementSibling;
                        if (!group) group = label.parentElement;
                        if (!group) return [];
                        const opts = [];
                        group.querySelectorAll('*').forEach(o => {
                            if (o.children.length > 0) return;  // 叶节点
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
        except Exception as e:
            logger.info(f"[Picker] _scrape_filters 失败: {e}")
            return {"rules": [], "categories": []}

    async def _scrape(self) -> tuple[list, bool]:
        """抓取当前面板所有商品/店铺。"""
        if self.current_type == "product":
            return await self._scrape_products()
        return await self._scrape_shops()

    async def _scrape_products(self) -> tuple[list, bool]:
        """抓取商品列表。

        锚点策略(避开 CSS Modules 哈希 class):
        - 当前激活的 ``[role="tabpanel"][aria-hidden="false"]`` 为范围(避免抓到隐藏 tab 的数据)
        - 商品链接 ``a[href*="item.taobao.com/item.htm"]`` 是每个商品卡都有的稳定锚点
        - 卡片 = 商品链接 + checkbox(``label.next-checkbox-wrapper``)的最小公共祖先
        - 标题从商品链接内的 ``span[title]`` 取
        - 价格从含 ``¥`` 前缀的叶节点文本取
        - 图片取卡片内 src 含 alicdn 的(主图)
        - 禁用从 ``input[type=checkbox]`` 的 ``disabled`` 属性判断
        - has_more 用激活 panel 内的"加载更多"/"没有更多了"文本判断
          (两个 tab panel 同时在 DOM,必须限定范围否则会误判)
        """
        try:
            data = await self.frame.evaluate(
                r"""() => {
                    const out = {items: [], has_more: false};
                    // 限定在激活的 tabpanel 内(隐藏 tab 的 DOM 还在,会污染数据)
                    const panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                    if (!panel) return out;
                    const root = panel;

                    const links = root.querySelectorAll('a[href*="item.taobao.com/item.htm"]');
                    const seenCards = new Set();
                    links.forEach(a => {
                        try {
                            // 向上找含 checkbox 的最近祖先 = 卡片(不超出 root)
                            let card = a.parentElement;
                            for (let i = 0; i < 10 && card && card !== root; i++) {
                                if (card.querySelector('label.next-checkbox-wrapper')) break;
                                card = card.parentElement;
                            }
                            if (!card || seenCards.has(card)) return;
                            seenCards.add(card);

                            // 标题 + id
                            const titleSpan = card.querySelector('a[href*="item.taobao.com/item.htm"] span[title], span[title]');
                            const title = titleSpan
                                ? (titleSpan.getAttribute('title') || titleSpan.textContent.trim())
                                : '';
                            const href = a.getAttribute('href') || '';
                            const m = href.match(/[?&]id=(\d+)/);
                            const itemId = m ? m[1] : '';

                            // 主图:src 含 alicdn
                            const imgs = Array.from(card.querySelectorAll('img'));
                            const mainImg = imgs.find(im => {
                                const s = im.getAttribute('src') || '';
                                return s.includes('alicdn.com');
                            }) || imgs[0];
                            const image = mainImg ? mainImg.getAttribute('src') : '';

                            // 价格:文本以 ¥ 开头的叶节点
                            let price = '';
                            const allEls = card.querySelectorAll('*');
                            for (const el of allEls) {
                                if (el.children.length > 0) continue;
                                const t = (el.textContent || '').trim();
                                if (t.startsWith('¥')) { price = t; break; }
                            }

                            // 已售
                            let sold = '';
                            for (const el of allEls) {
                                if (el.children.length > 0) continue;
                                const t = (el.textContent || '').trim();
                                if (t.startsWith('已售')) { sold = t; break; }
                            }
                            // 店铺名:启发式取非"已售"非"¥"的 span/a 文本
                            let shopName = '';
                            const shopCandidates = Array.from(card.querySelectorAll('span, a'))
                                .map(e => (e.textContent || '').trim())
                                .filter(t => t && t !== title && !t.startsWith('¥') && !t.startsWith('已售') && t.length <= 30);
                            if (shopCandidates.length) shopName = shopCandidates[shopCandidates.length - 1];

                            // 禁用:checkbox input 的 disabled 属性
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

                    // has_more: 只看激活 panel 内的文本
                    const panelTexts = Array.from(root.querySelectorAll('span, div'))
                        .map(e => (e.textContent || '').trim());
                    const hasMore = panelTexts.includes('加载更多');
                    const noMore = panelTexts.includes('没有更多了');
                    out.has_more = hasMore && !noMore;
                    return out;
                }"""
            )
            return data.get("items", []), data.get("has_more", False)
        except Exception as e:
            logger.info(f"[Picker] _scrape_products 失败: {e}")
            return [], False

    async def _scrape_shops(self) -> tuple[list, bool]:
        """抓取店铺列表。

        锚点策略:
        - 在当前激活的 ``[role="tabpanel"][aria-hidden="false"]`` 内找店铺卡
        - 店铺卡 = 含 ``label.next-radio-wrapper``(店铺选择 radio) + 含 ``<img>`` 的最小祖先
        - 店铺名 = 该卡内最长的链接文本(店铺通常有 ``<a>`` 链接)
        - 禁用 = ``input[type="radio"]`` 的 ``disabled`` 属性
        """
        try:
            data = await self.frame.evaluate(
                """() => {
                    const out = {items: [], has_more: false};
                    const panel = document.querySelector('[role="tabpanel"][aria-hidden="false"]');
                    if (!panel) return out;

                    const radios = panel.querySelectorAll('label.next-checkbox-wrapper, label.next-radio-wrapper');
                    const seen = new Set();
                    radios.forEach(label => {
                        try {
                            // 向上找同时含 img + 该 label 的祖先 = 店铺卡
                            let card = label.parentElement;
                            for (let i = 0; i < 8 && card && card !== panel; i++) {
                                if (card.querySelector('img')) break;
                                card = card.parentElement;
                            }
                            if (!card || seen.has(card)) return;
                            seen.add(card);

                            // 店铺名:卡内文本最长的链接(店铺通常有 a 链接)
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

                            // 已入手 N 件商品(可选)
                            let buyCount = '';
                            const allEls = card.querySelectorAll('*');
                            for (const el of allEls) {
                                if (el.children.length > 0) continue;
                                const t = (el.textContent || '').trim();
                                if (t.startsWith('已入手')) { buyCount = t; break; }
                            }

                            // 禁用:radio input 的 disabled 属性
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
        except Exception as e:
            logger.info(f"[Picker] _scrape_shops 失败: {e}")
            return [], False

    async def _teardown(self) -> None:
        """关闭浏览器,清空所有引用。"""
        for attr in ("context", "browser"):
            obj = getattr(self, attr, None)
            if obj is None:
                continue
            try:
                await obj.close()
            except Exception:
                pass
            setattr(self, attr, None)
        self.page = None
        self.frame = None
        self.current_type = None


# ----------------------------------------------------------------------
# 全局会话池
# ----------------------------------------------------------------------

class _SessionPool:
    """按 session_id 管理 GuanghePickerSession。

    session_id 命名: ``f"{account_id}"`` —— 同一账号同时只能开一个 picker。
    切换账号 = 关闭旧 session + 开新 session。
    """

    def __init__(self):
        self._sessions: dict[str, GuanghePickerSession] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> GuanghePickerSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def create(self, session_id: str, cookie_path: str) -> GuanghePickerSession:
        with self._lock:
            # 如果已存在,先标记需要替换;实际关闭在锁外做(避免阻塞)
            old = self._sessions.get(session_id)
            session = GuanghePickerSession(session_id, cookie_path)
            self._sessions[session_id] = session
        # 关旧会话(锁外,async)
        if old:
            asyncio.ensure_future(old._teardown())
        return session

    def remove(self, session_id: str) -> GuanghePickerSession | None:
        with self._lock:
            return self._sessions.pop(session_id, None)


pool = _SessionPool()
