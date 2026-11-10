# -*- coding: utf-8 -*-
"""EPUB 转纯文本。

思路：把 EPUB 拆成「章节化的纯文本缓存」，之后完全复用 TXT 的阅读链路
（同一套分页、搜索、书签、进度），不需要为 EPUB 单独写渲染。

输出格式（与常见 TXT 小说一致，带全角缩进）：

    第1章 标题
    　　正文段落一
    　　正文段落二

    第2章 标题
    ...

章节标题优先取 EPUB 自带目录（nav / ncx），取不到再退回文档里的 h1/h2。
"""
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from lxml import etree, html as lhtml

from .toc import Chapter

NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "o": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "x": "http://www.w3.org/1999/xhtml",
}

# 这些标签在 HTML 里是块级：前后要断开成独立段落
BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr",
    "blockquote", "section", "article", "header", "footer", "pre", "table",
}
SKIP_TAGS = {"script", "style", "head", "title", "meta", "link", "svg"}
INDENT = "\u3000\u3000"          # 全角缩进，与 TXT 小说的排版习惯一致
IMAGE_MARK = "\uff3b\u56fe\u7247\uff3d"      # ［图片］


@dataclass
class EpubInfo:
    title: str = ""
    author: str = ""
    opf_dir: str = ""
    spine: List[str] = field(default_factory=list)          # 文件名列表（按阅读顺序）
    nav_titles: dict = field(default_factory=dict)          # 文件名 -> 标题


@dataclass
class EpubResult:
    cache_path: str
    chapters: List[Chapter]
    title: str
    author: str
    chars: int
    spine_count: int


# ---------------------------------------------------------------- 解析元数据
def _read_info(z: zipfile.ZipFile) -> EpubInfo:
    info = EpubInfo()
    try:
        container = etree.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find(".//c:rootfile", NS)
        opf_path = rootfile.get("full-path") if rootfile is not None else None
    except (KeyError, etree.XMLSyntaxError):
        opf_path = None
    if not opf_path:
        # 兜底：直接找一个 .opf
        opf_path = next((n for n in z.namelist() if n.lower().endswith(".opf")), None)
    if not opf_path:
        raise ValueError("EPUB 里找不到 .opf 文件")

    opf = etree.fromstring(z.read(opf_path))
    base = os.path.dirname(opf_path)

    titles = [e.text for e in opf.findall(".//dc:title", NS) if e.text]
    authors = [e.text for e in opf.findall(".//dc:creator", NS) if e.text]
    info.title = (titles[0] if titles else "").strip()
    info.author = (authors[0] if authors else "").strip()

    manifest = {}
    for item in opf.findall(".//o:item", NS):
        manifest[item.get("id")] = (item.get("href") or "", item.get("media-type") or "",
                                    item.get("properties") or "")

    for itemref in opf.findall(".//o:itemref", NS):
        href, media, _props = manifest.get(itemref.get("idref"), ("", "", ""))
        if not href:
            continue
        if "html" not in media and not href.lower().endswith((".html", ".xhtml", ".htm")):
            continue
        info.spine.append(_join(base, href))

    # 目录：EPUB3 nav 优先，其次 EPUB2 ncx
    for _id, (href, media, props) in manifest.items():
        full = _join(base, href)
        if "nav" in props:
            info.nav_titles = _parse_nav(z, full)
            break
    if not info.nav_titles:
        for _id, (href, media, _props) in manifest.items():
            if "dtbncx" in media or full.endswith(".ncx"):
                info.nav_titles = _parse_ncx(z, _join(base, href))
                break

    info.opf_dir = base
    return info


def _join(base: str, href: str) -> str:
    href = href.split("#")[0]
    if base and not href.startswith(base + "/"):
        return "%s/%s" % (base, href.lstrip("./"))
    return href


def _parse_nav(z: zipfile.ZipFile, path: str) -> dict:
    """EPUB3 nav.xhtml：把链接文本按目标文件记下来。"""
    out = {}
    try:
        doc = lhtml.fromstring(z.read(path))
    except (KeyError, etree.XMLSyntaxError):
        return out
    base = os.path.dirname(path)
    for a in doc.xpath("//a[@href]"):
        target = a.get("href").split("#")[0]
        text = (a.text_content() or "").strip()
        if not target or not text:
            continue
        full = _join(base, target)
        out.setdefault(full, text)      # 同一文件只取第一条
    return out


def _parse_ncx(z: zipfile.ZipFile, path: str) -> dict:
    """EPUB2 toc.ncx：navPoint -> content@src + navLabel/text。"""
    out = {}
    try:
        doc = etree.fromstring(z.read(path))
    except (KeyError, etree.XMLSyntaxError):
        return out
    base = os.path.dirname(path)
    for point in doc.findall(".//ncx:navPoint", NS):
        label = point.find(".//ncx:navLabel/ncx:text", NS)
        content = point.find("ncx:content", NS)
        if label is None or content is None:
            continue
        text = (label.text or "").strip()
        src = content.get("src") or ""
        if not text or not src:
            continue
        out.setdefault(_join(base, src), text)
    return out


# ---------------------------------------------------------------- 抽正文
HEADING_TAGS = {"h1", "h2", "h3"}


def _extract(raw: bytes):
    """把一个 XHTML 拆成 (段落列表, 第一个标题文本)。"""
    try:
        root = lhtml.fromstring(raw)
    except (etree.XMLSyntaxError, ValueError):
        return [], ""

    paras: List[str] = []
    buf: List[str] = []
    heading = [""]

    def flush():
        text = "".join(buf).strip()
        buf.clear()
        if text:
            paras.append(text)

    def walk(node):
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag in SKIP_TAGS:
            return
        if tag in ("br", "hr"):
            buf.append("\n")
            return
        if tag == "img":
            buf.append(IMAGE_MARK)
            return
        is_block = tag in BLOCK_TAGS
        if is_block:
            flush()
        if tag in HEADING_TAGS and not heading[0]:
            # 标题只在段落边界上取，避免把半个句子当标题
            text = (node.text_content() or "").strip()
            if text and len(text) <= 60 and text != IMAGE_MARK:
                heading[0] = _clean(text)
        if node.text:
            buf.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                buf.append(child.tail)
        if is_block:
            flush()

    body = root.find(".//body")
    walk(body if body is not None else root)
    flush()
    return paras, heading[0]


def _clean(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"[ \t\u00a0]+", " ", text).strip()


# ---------------------------------------------------------------- 主流程
def convert(epub_path: str, cache_path: str,
            progress: Optional[Callable[[int, int], bool]] = None) -> EpubResult:
    """把 EPUB 转成纯文本缓存。progress(done, total) 返回 False 表示取消。"""
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    chapters: List[Chapter] = []
    total_chars = 0

    with zipfile.ZipFile(epub_path) as z:
        info = _read_info(z)
        total = len(info.spine)
        offset = 0
        tmp_path = cache_path + ".part"
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            for idx, name in enumerate(info.spine):
                if progress is not None and not progress(idx, total):
                    break
                try:
                    raw = z.read(name)
                except KeyError:
                    continue
                paras, heading = _extract(raw)
                paras = [_clean(p) for p in paras]
                paras = [p for p in paras if p]
                if not paras:
                    continue

                # 标题优先级：EPUB 目录 > 文档里的 h1/h2/h3 > 兜底
                title = (info.nav_titles.get(name) or heading or "").strip()
                if idx == 0 and (not title or title == IMAGE_MARK or title == info.title):
                    title = "封面"          # 首页通常是封面 + 简介，别让书名重复出现
                elif not title or title == IMAGE_MARK:
                    title = "第 %d 节" % (idx + 1)
                # 标题若与正文首段重复，去掉重复的那段
                if paras and paras[0] == title:
                    paras = paras[1:]
                if not paras:
                    continue

                block = "%s\n%s\n\n" % (title, "\n".join(INDENT + p for p in paras))
                data = block.encode("utf-8")
                chapters.append(Chapter(level=2, title=title, offset=offset))
                f.write(block)
                offset += len(data)
                total_chars += len(block)

        if len(tmp_path):
            os.replace(tmp_path, cache_path)

    return EpubResult(cache_path=cache_path, chapters=chapters,
                      title=info.title, author=info.author,
                      chars=total_chars, spine_count=total)


def cache_name(book_id: int) -> str:
    return "epub_%d.txt" % int(book_id)


def read_meta(epub_path: str):
    """只读元数据（不转换正文），导入时用来填书名/作者。失败返回 ("","")。"""
    try:
        with zipfile.ZipFile(epub_path) as z:
            info = _read_info(z)
        return info.title, info.author
    except (OSError, KeyError, ValueError, etree.XMLSyntaxError):
        return "", ""
