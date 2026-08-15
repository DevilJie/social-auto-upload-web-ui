"""京东关联商品 picker — 帧级纯函数 DOM 操作库。

所有函数以 frame-like 对象(Page 或 Frame)为参数。
京东 dr.jd.com 是微前端架构,发布表单实际在内嵌 iframe 里:
- top frame: https://dr.jd.com/jm/#/n/publish-video.html (主壳,只有"猜你想问"FAQ)
- iframe:    https://dr.jd.com/n/publish-video.html     (实际表单)
调用方应传 iframe(picker.py 已对齐);旧调用方传 Page 也兼容(见 _page_of)。
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

from dataclasses import dataclass, field


# ---------- trace 签名 ----------

def trace_signature(trace: dict) -> tuple[str, int]:
    """trace 签名:(keyword, page)。"""
    return (trace.get("keyword", ""), trace.get("page", 1))


def _page_of(frame):
    """从 frame-like 对象取 Page —— 用于 keyboard 等 Page-only API。

    Playwright Python 的 Page 和 Frame API 不对称:
    - Page 有 keyboard 属性,Frame 没有
    - Frame 有 page 属性(注意:是 property 不是方法,直接 frame.page 不加括号),
      Page 没有 page 属性

    本模块函数既能接受 Page(旧用法,top frame) 也能接受 Frame(新用法,iframe),
    靠这个 helper 统一拿 Page。
    """
    if hasattr(frame, "keyboard"):
        return frame  # 已经是 Page
    # Frame.page 是 property(返回 Page 对象,不是 bound method)
    # 用 callable 兜底:万一未来 Playwright 改回方法也能 work
    page_attr = frame.page
    return page_attr() if callable(page_attr) else page_attr


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


async def wait_publish_frame(page, timeout: float = 20):
    """等京东发布表单所在的 iframe 出现并返回。

    京东 dr.jd.com 是微前端架构,发布表单在内嵌 iframe 里(已实证):
    - top frame URL: https://dr.jd.com/jm/#/n/publish-video.html (主壳,只有"猜你想问"FAQ)
    - iframe    URL: https://dr.jd.com/n/publish-video.html     (实际表单,radio/file_input/addgoods 都在这)

    通过 URL path 含 '/n/publish-video.html' 且 URL 里没 '#' 来识别 iframe
    (top frame 的 hash 路由是 '#/n/publish-video.html',会含 '#')。

    picker.py 和 platform.py 共用此函数 —— 之前两处各自维护一份,
    发现 bug 时容易只改一处遗漏另一处(参见 picker 最初的 iframe bug)。
    """
    import asyncio
    attempts = max(1, int(timeout / 0.3))
    for _ in range(attempts):
        for f in page.frames:
            if f == page.main_frame:
                continue
            url = f.url or ""
            if "/n/publish-video.html" in url and "#" not in url:
                return f
        await asyncio.sleep(0.3)
    raise RuntimeError(
        f"未找到发布表单 iframe (timeout={timeout}s)。"
        f" 当前 frames: {[f.url for f in page.frames]}"
    )


# ---------- 商品抓取 ----------

async def scrape_total(frame) -> int:
    """从 .jd-pagination-total-text 抓"共 N 条"解析出总条数。

    DOM 形如: <li class="jd-pagination-total-text">共 1 条</li>
    解析失败 / 元素不存在时返回 0(前端兜底按当前页条数估算)。
    """
    el = await frame.query_selector(".jd-pagination-total-text")
    if not el:
        return 0
    txt = (await el.inner_text()).strip()
    digits = "".join(c for c in txt if c.isdigit())
    return int(digits) if digits else 0


async def scrape_products(frame) -> list[dict]:
    """抓当前激活面板的商品列表 -> [{title, image, id, price, shop_name}, ...]。

    商品 id 提取优先级:
    1. 从图片 URL 提取:    //m.360buyimg.com/.../{skuId}.png
    2. 兜底: 用 .jd-checkbox-input 的 value 或 dataset
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
    用 JS click 绕过可能的浮层遮挡(Playwright .click() 要求可见+无遮挡)。
    """
    # 等元素存在(attached),不要求 visible
    await frame.wait_for_selector(
        ".addgoods-upload[data-spm-click='publishGoodsAddGood']",
        timeout=10_000,
        state="attached",
    )
    # JS click 不受遮挡影响
    clicked = await frame.evaluate(
        """() => {
            const el = document.querySelector(
                ".addgoods-upload[data-spm-click='publishGoodsAddGood']"
            );
            if (el) { el.click(); return true; }
            return false;
        }"""
    )
    if not clicked:
        raise RuntimeError("未找到 .addgoods-upload 元素")


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


# ---------- 搜索 ----------

async def _find_search_input(frame):
    """找搜索 input,本店商品 tab 优先,站内搜索/兜底也试。

    DOM 锚点优先级:
    1. ._my-goods-container-head_aejm5_69 .jd-input   (本店商品 tab)
    2. .search-input-content-input                    (站内搜索 tab)
    3. .jd-drawer-wrapper-body .jd-input              (兜底:抽屉里任何 input)
    """
    for selector in (
        "._my-goods-container-head_aejm5_69 .jd-input",
        ".search-input-content-input",
        ".jd-drawer-wrapper-body .jd-input",
    ):
        inp = await frame.query_selector(selector)
        if inp:
            return inp
    return None


async def search(frame, keyword: str):
    """清空 input + (可选)填入 keyword + 总是按回车 + 等结果。

    关键设计:
    - **总是按回车**(即使 keyword 为空):让京东从过滤状态恢复"全部商品",
      否则前端清空关键词后页面不刷新,scrape 拿到的还是上次搜索结果。
    - **清空用 triple_click + Delete** 而非 fill(''):对 React 受控 input 更可靠。
    - **等卡片 OR 空状态**:0 结果时不再吃满 10s 超时(wait_search_results)。
    """
    # 轮询等搜索框出现(抽屉刚打开时搜索框可能还没渲染完,立即查会"未找到搜索框")
    inp = None
    for _ in range(30):  # 30 * 0.3s ≈ 9s
        inp = await _find_search_input(frame)
        if inp:
            break
        await sleep(0.3)
    if not inp:
        raise RuntimeError("未找到搜索框")

    # 1. 清空 input(triple_click 选中所有 + Delete,React onChange 友好)
    await inp.click(click_count=3)
    await _page_of(frame).keyboard.press("Delete")
    await sleep(0.2)

    # 2. 填入 keyword(非空才填)
    if keyword:
        await inp.fill(keyword)
        await sleep(0.3)

    # 3. 总是按回车触发搜索(空 keyword = 京东恢复"全部商品")
    await _page_of(frame).keyboard.press("Enter")

    # 4. 等结果稳定
    await wait_search_results(frame)


async def wait_search_results(frame, timeout: float = 10):
    """等搜索结果稳定:**卡片 OR 空状态**任一出现就返回。

    之前只等 ._sku-card-mygoods-con_jvzh5_77,0 结果时永远等不到,吃满 10s 超时。
    现在加上 ._empty-container_1xak8_69(空状态 DOM),空结果秒返回。
    """
    try:
        await frame.wait_for_selector(
            "._sku-card-mygoods-con_jvzh5_77, ._empty-container_1xak8_69",
            timeout=timeout * 1000,
            state="visible",
        )
    except Exception:
        pass  # 兜底:超时也继续(让 scrape 抓当前状态)
    await sleep(0.3)


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
        checkbox_label = await card.query_selector(".jd-checkbox-wrapper")

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

        page_ids.append((sku_id, card, checkbox_label, is_checked, is_disabled))

    # 桶分类
    found_ids = {pid for pid, *_ in page_ids}
    for tid in target_ids:
        if tid not in found_ids:
            result.missing.append(tid)

    for pid, card, checkbox_label, is_checked, is_disabled in page_ids:
        if pid not in target_set:
            continue
        if is_disabled:
            result.disabled.append(pid)
            continue
        if is_checked:
            result.already.append(pid)
            continue
        # 勾选:点 label(.jd-checkbox-wrapper 包裹 input,触发 React 勾选)。
        # 直接点 .jd-checkbox-input(input 是 display:none)不触发勾选。
        # 点击后必须等 React setState 更新完成,否则「确定」会先于勾选生效。
        try:
            if checkbox_label:
                await checkbox_label.click()
                result.checked.append(pid)
                await sleep(0.5)
            else:
                # 退而求其次:点整张卡片
                await card.click()
                result.checked.append(pid)
                await sleep(0.5)
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
            await _page_of(frame).keyboard.press("Escape")
        await sleep(0.5)
    except Exception:
        pass


# ---------- 小说下拉 ----------

async def wait_novel_dropdown(frame, timeout: float = 10):
    """等小说下拉框出现(rc-virtual-list-holder-inner)。"""
    await frame.wait_for_selector(
        ".rc-virtual-list-holder-inner",
        timeout=timeout * 1000,
        state="visible",
    )


async def scrape_novels(frame) -> list[dict]:
    """从当前下拉 DOM 抓小说候选列表。

    返回:[{title, image, category, read_count, id}, ...]
    - title:       .related-book-item-right-name inner_text
    - image:       .crefe-custom-image[src]
    - category:    .related-book-item-right-info 拆分 "|" 取 [0]
    - read_count:  .related-book-item-right-info 拆分 "|" 取 [1] 中数字
    - id:          留空字符串(DOM 里没有 book id,发布时按 title 选中即可,
                   见 platform._select_novel)

    注意:DOM 锚点参考用户提供的 2026-08-14 京东发布页快照。
    """
    items: list[dict] = []
    options = await frame.query_selector_all(
        ".rc-virtual-list-holder-inner .jd-select-item-option"
    )
    for opt in options:
        try:
            name_el = await opt.query_selector(".related-book-item-right-name")
            img_el = await opt.query_selector(".crefe-custom-image")
            info_el = await opt.query_selector(".related-book-item-right-info")

            title = (await name_el.inner_text()).strip() if name_el else ""
            image = (await img_el.get_attribute("src") or "") if img_el else ""
            info = (await info_el.inner_text()).strip() if info_el else ""

            # info 形如 "音乐舞蹈 | 142人已读"
            category = ""
            read_count = ""
            if info:
                parts = [p.strip() for p in info.split("|")]
                if parts:
                    category = parts[0]
                if len(parts) >= 2:
                    digits = "".join(c for c in parts[1] if c.isdigit())
                    read_count = digits

            items.append({
                "id": "",
                "title": title,
                "image": image,
                "category": category,
                "read_count": read_count,
            })
        except Exception:
            continue
    return items


async def search_novels(frame, keyword: str) -> list[dict]:
    """打开小说 select + 输入 keyword + 等下拉 + 抓候选(不选中)。

    用于前端下拉搜索预览(选中的逻辑在 select_novel,发布时调用)。

    DOM 锚点(参考用户提供的 2026-08-14 快照):
    - 小说 select: .jd-select-show-search(切到 novel radio 后出现)
    - 搜索 input:  .jd-select-selection-search-input
    - 下拉项容器: .rc-virtual-list-holder-inner
    """
    # 1. 点开小说 select(若未展开)
    select = await frame.wait_for_selector(".jd-select-show-search", timeout=10_000)
    is_expanded = await select.evaluate(
        """el => {
            const input = el.querySelector('input');
            return input ? input.getAttribute('aria-expanded') === 'true' : false;
        }"""
    )
    if not is_expanded:
        await select.click()
        await sleep(0.3)

    # 2. 清空搜索 input(triple_click + Delete,React 受控 input 友好)
    #    注意:页面有 3 个 .jd-select-selection-search-input(小说/创作声明/定时发布),
    #    小说那个是非 readonly 且在当前展开的 .jd-select-show-search 里。
    #    press_sequentially 是 Locator 方法,所以用 frame.locator() 拿 Locator。
    search_input = frame.locator(
        ".jd-select-show-search .jd-select-selection-search-input:not([readonly])"
    )
    await search_input.click(click_count=3)
    await _page_of(frame).keyboard.press("Delete")
    await sleep(0.2)

    # 3. 输入 keyword(非空才输)
    if keyword:
        # press_sequentially 逐字输入,React onChange 友好(参考 CLAUDE.md §6)
        await search_input.press_sequentially(keyword, delay=100)

    # 4. 等下拉出现(空 keyword 时下拉会显示历史/热门,也试着抓)
    try:
        await frame.wait_for_selector(
            ".rc-virtual-list-holder-inner .jd-select-item-option",
            timeout=5_000,
            state="visible",
        )
    except Exception:
        pass  # 兜底:超时也继续,让 scrape 抓当前
    await sleep(0.3)

    # 5. 抓候选
    return await scrape_novels(frame)


async def select_novel(frame, novel_title: str):
    """在小说下拉中按 title 文本选择。

    步骤:
    1. 点击小说 .jd-select(jd-select-show-search)
    2. 在搜索 input 内 type 关键词
    3. 等下拉出现 .rc-virtual-list-holder-inner
    4. 找含 novel_title 的 .jd-select-item-option
    5. click 选中

    DOM 锚点:
    - 小说 select: 关联挂件 radio 切到 novel 后出现的 .jd-select(.jd-select-show-search)
    - 下拉项:    .jd-select-item-option .related-book-item-right-name
    """
    # 1. 找到小说 select 并点击
    select = await frame.wait_for_selector(
        ".jd-select-show-search",
        timeout=10_000,
    )
    await select.click()
    await sleep(0.5)

    # 2. 找到搜索 input 并 type
    #    小说搜索框是非 readonly 且在当前展开的 .jd-select-show-search 里,
    #    页面另有两个 readonly 的同名 input(创作声明/定时发布),必须排除。
    #    press_sequentially 是 Locator 方法,这里用 frame.locator() 而非
    #    wait_for_selector(返回 ElementHandle,没有 press_sequentially)
    search_input = frame.locator(
        ".jd-select-show-search .jd-select-selection-search-input:not([readonly])"
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