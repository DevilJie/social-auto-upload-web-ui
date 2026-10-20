# -*- coding: utf-8 -*-
"""文章发布通用 HTML 工具：图片提取/替换、轻量清洗。

文章发布的正文由前端富文本编辑器产出标准 HTML（img src 指向本地
素材库 ``/api/materials/file/<stored_path>``）。各平台自动化写入正文前
需要把本地图片换成平台 CDN URL（如公众号 filetransfer → mmbiz.qpic.cn），
本模块负责与平台无关的 HTML 层处理。

实现用标准库 html.parser（不引入 bs4/lxml 新依赖）：
- extract_img_srcs(html)   -> list[str]        按 HTML 中出现顺序提取 img src
- replace_img_srcs(html, mapping) -> str       按 src 精确替换 img 的 src 属性
- sanitize_article_html(html) -> str           去 script/style/iframe 与 on* 属性

约定：其余标签、属性、内联样式**原样保留**（公众号等编辑器粘贴时
会自行规范化，平台差异交给各平台适配层处理）。
"""

from __future__ import annotations

from html.parser import HTMLParser

# 整体丢弃的标签（含内容）。前端编辑器输出可控，黑名单只做兜底。
_DROP_WITH_CONTENT = {"script", "style"}
_DROP_TAG_ONLY = {"iframe", "object", "embed", "link", "meta"}

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _ArticleHTMLTransformer(HTMLParser):
    """单遍解析 → 重建 HTML。

    - img.src 在 mapping 中则替换（其余属性原样保留）
    - script/style 连内容一起丢；iframe/object/embed/link/meta 丢标签
    - on* 属性与 javascript: 协议属性剔除
    """

    def __init__(self, img_mapping: dict[str, str] | None = None,
                 sanitize: bool = False):
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        self._img_mapping = img_mapping or {}
        self._sanitize = sanitize
        self._drop_depth = 0  # >0 表示正处于丢弃标签内部

    # ---- token 收集 ----

    def _clean_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
        if not self._sanitize:
            return attrs
        cleaned = []
        for name, value in attrs:
            low = name.lower()
            if low.startswith("on"):
                continue
            if low in ("href", "src") and value and value.strip().lower().startswith("javascript:"):
                continue
            cleaned.append((name, value))
        return cleaned

    @staticmethod
    def _format_attrs(attrs: list[tuple[str, str | None]]) -> str:
        parts = []
        for name, value in attrs:
            if value is None:
                parts.append(name)
            else:
                escaped = (value.replace("&", "&amp;").replace('"', "&quot;"))
                parts.append(f'{name}="{escaped}"')
        return (" " + " ".join(parts)) if parts else ""

    def handle_decl(self, decl: str):
        if self._drop_depth == 0:
            self._out.append(f"<!{decl}>")

    def handle_pi(self, data: str):
        if self._drop_depth == 0:
            self._out.append(f"<?{data}>")

    def unknown_decl(self, data: str):
        if self._drop_depth == 0:
            self._out.append(f"<![{data}]>")

    def handle_comment(self, data: str):
        if self._drop_depth == 0:
            self._out.append(f"<!--{data}-->")

    def handle_entityref(self, name: str):
        if self._drop_depth == 0:
            self._out.append(f"&{name};")

    def handle_charref(self, name: str):
        if self._drop_depth == 0:
            self._out.append(f"&#{name};")

    def handle_data(self, data: str):
        if self._drop_depth == 0:
            self._out.append(data)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            self._drop_depth += 1
            return
        if self._drop_depth:
            return  # 丢弃标签内部的任何嵌套内容
        if tag in _DROP_TAG_ONLY:
            return
        if tag == "img":
            self._emit_img(attrs)
            return
        self._out.append(
            f"<{tag}{self._format_attrs(self._clean_attrs(tag, attrs))}>"
        )

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            return  # 自闭合 script/style 不存在内容，直接丢
        if self._drop_depth:
            return
        if tag in _DROP_TAG_ONLY:
            return
        if tag == "img":
            self._emit_img(attrs, self_closing=True)
            return
        self._out.append(
            f"<{tag}{self._format_attrs(self._clean_attrs(tag, attrs))}/>"
            if tag in _VOID_TAGS
            else f"<{tag}{self._format_attrs(self._clean_attrs(tag, attrs))}>"
        )

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_WITH_CONTENT:
            if self._drop_depth:
                self._drop_depth -= 1
            return
        if self._drop_depth or tag in _DROP_TAG_ONLY:
            return
        # 空元素不输出闭合（浏览器容错，但输出更干净）
        if tag in _VOID_TAGS:
            return
        self._out.append(f"</{tag}>")

    # ---- img 特殊处理 ----

    def _emit_img(self, attrs, self_closing: bool = False):
        new_attrs = []
        for name, value in attrs:
            if name.lower() == "src" and value and value in self._img_mapping:
                value = self._img_mapping[value]
            elif name.lower() == "src" and value and self._img_mapping:
                # 无协议相对 URL 兜底精确匹配失败时保留原值
                pass
            new_attrs.append((name, self._sanitize_attr_value(name, value)))
        suffix = " /" if self_closing else ""
        self._out.append(f"<img{self._format_attrs(new_attrs)}{suffix}>")

    def _sanitize_attr_value(self, name: str, value: str | None) -> str | None:
        if not self._sanitize:
            return value
        if name.lower() == "src" and value and value.strip().lower().startswith("javascript:"):
            return ""
        return value

    def result(self) -> str:
        return "".join(self._out)


def _transform(html: str, img_mapping: dict[str, str] | None, sanitize: bool) -> str:
    parser = _ArticleHTMLTransformer(img_mapping=img_mapping, sanitize=sanitize)
    parser.feed(html or "")
    parser.close()
    return parser.result()


def extract_img_srcs(html: str) -> list[str]:
    """按出现顺序提取正文里的 img src（去重保序）。"""
    srcs: list[str] = []

    class _Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag.lower() == "img":
                for name, value in attrs:
                    if name.lower() == "src" and value:
                        srcs.append(value)
                        return

        handle_startendtag = handle_starttag

    collector = _Collector(convert_charrefs=False)
    collector.feed(html or "")
    collector.close()
    return list(dict.fromkeys(srcs))


def replace_img_srcs(html: str, mapping: dict[str, str]) -> str:
    """把 html 中 img 的 src 按 mapping 精确替换。未命中的保持原样。"""
    if not mapping:
        return html or ""
    return _transform(html, img_mapping=mapping, sanitize=False)


def sanitize_article_html(html: str) -> str:
    """轻量清洗：去 script/style 内容、iframe 等标签、on*/javascript: 属性。"""
    return _transform(html, img_mapping=None, sanitize=True)


def count_text_length(html: str) -> int:
    """正文纯文本长度（去标签，供字数校验用）。"""
    text: list[str] = []

    class _Text(HTMLParser):
        def handle_data(self, data: str):
            text.append(data)

    parser = _Text(convert_charrefs=True)
    parser.feed(html or "")
    parser.close()
    return len("".join(text).strip())
