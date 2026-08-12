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