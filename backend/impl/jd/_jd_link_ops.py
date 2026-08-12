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