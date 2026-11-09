#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成性能基准用的中文测试语料（本地生成，不联网）。

用法:  python gen_corpus.py [输出目录] [目标大小MB]
默认:  ./corpus, 100 MB
"""
import os
import sys
import random

random.seed(20240501)

# 常见汉字样本（高频 + 中频混合，尽量接近真实小说/文档分布）
HANZI = (
    "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出也得里后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开美总从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间斯知世什两次使身者被高已亲其进此话常与活正感"
    "见明问力理尔点文几定本公特做外孩相西果走将月十实向声车全信重三机工物气每并别真打太新比才便夫再书部水像眼等体却加电主界门利海受听表德少克代员许稜先口由死安写性马光白或住难望教命花结乐色更拉东神记处让母父应直字场平报友关放至张认接告入笑内英军候民岁往何度山觉路带万男边风解叫任金快原吃妈变通师立象数四失满战远格士音轻目条呢病始达深完今提求清王化空业思切怎非找片罗钱吗语元喜曾离飞科言干流欢约各即指合反题必该论交终林请医晚制球决传画保读运及则房早院量苦火布品近坐产答星精视五连司巴奇管类未朋且婚台夜青北队久乎越观落尽形影红爸百令周吧识步希亚术留市半热送兴造谈容极随演收首根讲整式取照办强石古华諣拿计您装似足双妻尼转诉米称丽客南领节衣站黑刻统断福城故历惊脸选包紧争另建维绝树系伤示愿持千史谁准联妇纪基买志静阿诗独复痛消社算义竟确酒需单治卡幸兰念举仅钟怕共毛句息功官待究跟穿室易游程号居考突皮哪费倒价图具刚脑永歌响商礼细专黄块脚味灵改据般破引食仍存众注笔甚某沉血备习校默务土微娘须试怀料调广苏显赛查密议底列富梦错座参八除跑亮假印设线温虽掉京初养香停际致阳纸李纳验助激够严证帝饭忘趣支春集丈木研班普导顿睡展跳获艺六波察群皇段急庭创区奥器谢弟店否害草排背止组州朝封睛板角况曲馆育忙质河续哥呼若推境遇雨标姐充围案伦护冷警贝著雪索剧啊船险烟依斗值帮汉慢佛肯闻唱沙局伯族低玩资屋击速顾泪洲团圣旁堂兵七露园牛哭旅街劳型烈姑陈莫鱼异抱宝权鲁简态级票怪寻杀律胜份汽右洋范床舞秘午登楼贵吸责例追较职属渐左录丝牙党继托赶章智冲叶胡吉卖坚喝肉遗救修松临藏担戏善卫药悲敢靠伊村戴词森耳差短祖云规窗散迷油旧适乡架恩投弹铁博雷府压超负勒杂醒洗采毫嘴毕九冰既状乱景席珍童顶派素脱农疑练野按坏坐帝"
)

ASCII_WORDS = [
    "server", "timeout", "request", "response", "latency", "buffer", "thread",
    "index", "offset", "render", "layout", "parse", "encode", "decode", "cache",
    "the", "and", "with", "for", "from", "this", "that", "which", "value",
    "HTTP", "JSON", "UTF-8", "GBK", "API", "CPU", "SQL", "EPUB", "TXT",
]

PUNCT = "，。！？；：、"

CHAPTER_KINDS = [
    "第{n}章 {title}",
    "第{n}回合 {title}",
    "Chapter {n}: {title}",
]

TITLES = [
    "夜色渐深", "风起时", "旧日回声", "山雨欲来", "长夜将至", "归途", "无名之人",
    "断 sword 之约", "城南旧事", "一纸空文", "云深不知处", "灯下故人",
]


def sentence():
    """生成一句 15~60 字的中英混排句子。"""
    n = random.randint(15, 60)
    out = []
    while len(out) < n:
        r = random.random()
        if r < 0.06:
            out.append(random.choice(ASCII_WORDS))
        elif r < 0.10:
            out.append(str(random.randint(0, 9999)))
        else:
            out.append(random.choice(HANZI))
    s = "".join(out)
    if random.random() < 0.08:
        s = s + "，" + "".join(random.choice(ASCII_WORDS) for _ in range(random.randint(1, 3)))
    return s + random.choice(PUNCT)


def paragraph():
    return "".join(sentence() for _ in range(random.randint(3, 9)))


def block(n_chapters):
    parts = []
    for i in range(n_chapters):
        kind = random.choice(CHAPTER_KINDS).replace("{n}", str(i + 1))
        kind = kind.replace("{title}", random.choice(TITLES))
        parts.append(kind)
        parts.append("")
        for _ in range(random.randint(18, 40)):
            parts.append("　　" + paragraph())
            parts.append("")
    return "\n".join(parts)


def gen_txt(path, size_mb):
    target = size_mb * 1024 * 1024
    chunk_chars = 4000  # 每章约 4k 字
    written = 0
    chapters = 0
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        while written < target:
            chapters += 1
            b = block(1).replace("第1章", "第%d章" % chapters).replace("第1回合", "第%d回合" % chapters)
            b = b.replace("Chapter 1:", "Chapter %d:" % chapters)
            f.write(b)
            if not b.endswith("\n"):
                f.write("\n")
            written += len(b.encode("utf-8"))
    return path, written, chapters


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "corpus"
    size_mb = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    os.makedirs(out_dir, exist_ok=True)

    big = os.path.join(out_dir, "big_%dmb.txt" % size_mb)
    if not (os.path.exists(big) and os.path.getsize(big) > size_mb * 1024 * 1024 * 0.99):
        p, n, ch = gen_txt(big, size_mb)
        print("generated %s  %.1f MB  %d chapters" % (p, n / 1048576, ch))
    else:
        print("reuse %s  %.1f MB" % (big, os.path.getsize(big) / 1048576))

    # 边界用例 1: 无换行的超长单行（5 MB）
    oneline = os.path.join(out_dir, "oneline.txt")
    if not os.path.exists(oneline):
        with open(oneline, "w", encoding="utf-8", newline="") as f:
            f.write("".join(sentence() for _ in range(1)) * 0)
            reps = 5 * 1024 * 1024 // 60
            f.write(("这是一个没有换行的超长单行文本" * 1) * (reps // 15))
        print("generated %s  %.1f MB (single line)" % (oneline, os.path.getsize(oneline) / 1048576))

    # 边界用例 2: GBK 编码的 20MB 文本，用于编码识别
    gbk = os.path.join(out_dir, "gbk_20mb.txt")
    if not os.path.exists(gbk):
        src = os.path.join(out_dir, "_gbk_src.txt")
        gen_txt(src, 20)
        with open(src, encoding="utf-8") as fi, open(gbk, "wb") as fo:
            fo.write(fi.read().encode("gbk", errors="ignore"))
        os.remove(src)
        print("generated %s  %.1f MB (gbk)" % (gbk, os.path.getsize(gbk) / 1048576))

    for name in sorted(os.listdir(out_dir)):
        p = os.path.join(out_dir, name)
        print("  %-16s %8.2f MB" % (name, os.path.getsize(p) / 1048576))


if __name__ == "__main__":
    main()
