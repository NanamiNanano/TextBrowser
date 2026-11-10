# 文本浏览器（TextBrowser）

Windows 桌面端 TXT / EPUB 阅读器。为**超大文本**与**长时间沉浸阅读**设计：
100 MB 中文 TXT 秒开、翻页 4 ms、内存 77 MB。

## 特性

- **大文件不卡**：mmap + 切片分页，翻页延迟与文件大小无关
- **两种阅读模式**：分页（一页一屏）与连续滚动，`Ctrl+M` 随时切换且不丢位置
- **外观全可调**：设置面板 + 5 套预设主题；背景色可用屏幕取色器从任意画面吸取
- **无边框窗口**：自绘标题栏、保留系统贴边吸附、四边四角可缩放
- **托盘常驻**：`ESC` 收进托盘，`Q` / `E` 翻页
- **进度不丢**：以字节偏移为基准，改字号/换窗口/换模式都不错位
- **TXT 与 EPUB**：EPUB 自动转成章节化纯文本缓存，与 TXT 共用同一套阅读/搜索/书签链路（10 MB / 1587 文件实测 1.1 s）
- **目录识别**：TXT 章节正则识别（真实 12 MB 小说 982 章无缺失）+ EPUB 内建目录；后台线程识别，不卡首屏
- **搜索 / 书签**：全文搜索（100 MB 约 35–130 ms）、页内高亮、书签增删跳转

## 环境

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 10 1809+ / Windows 11 x64 |
| Python | 3.10+（实测 3.12.0 / 3.12.14） |
| 依赖 | PySide6-Essentials 6.12（装在 `vendor/py312`） |

## 安装依赖

项目不依赖系统 site-packages，PySide6 放在 `vendor/py312` 里，随项目走。

```powershell
.\scripts\bootstrap.ps1
```

（该脚本从华为云镜像下载 wheel 并解压；不经过 pip，因为 pip 在受限环境下会因
临时文件删除被拒而失败。）

## 运行

```powershell
.\scripts\run.ps1                    # 开发模式（带控制台，能看到报错）
.\scripts\run.ps1 某本书.txt          # 打开指定文件
```

双击入口：`.\\文本浏览器.lnk`（用 `scripts\make_shortcut.ps1` 生成）。

## 快捷键

| 键 | 功能 |
| --- | --- |
| `ESC` | 最小化到托盘 |
| `Q` / `E` | 上一页 / 下一页（滚动模式下为上一屏 / 下一屏；`←` `→` `PgUp` `PgDn` `空格` 同效） |
| `Ctrl+T` | 目录侧栏 |
| `Ctrl+F` | 搜索侧栏 |
| `Ctrl+M` | 切换分页 / 滚动 |
| `Ctrl+,` | 设置面板 |
| `Ctrl+O` | 导入文件 |
| `Ctrl+W` | 关闭文档回书架 |
| `Ctrl+=` / `Ctrl+-` | 字号增减 |
| `F11` | 最大化 / 还原 |

输入框聚焦时，所有单键快捷键（含 `ESC`）自动让位，不会被当成翻页。

## 测试

```powershell
.\scripts\test.ps1                   # 93 项断言：核心层 / 目录 / 搜索 / 阅读器 / 阅读模式 / 设置取色 / 真实文件
```

可视化自查（不需要人盯屏幕）：

```powershell
python -m app.tests.shot_ui          # 渲染 PNG 到 docs/shots/
```

## 目录结构

```
app/
├─ config.py            路径与常量
├─ main.py              入口：单实例、主题、命令行
├─ core/                纯逻辑，不依赖界面
│  ├─ encoding.py       编码识别
│  ├─ textfile.py       mmap、行索引、字符边界对齐
│  ├─ paginate.py       切片分页引擎
│  ├─ toc.py            目录（章节）识别
│  ├─ epub.py           EPUB 转纯文本
│  ├─ search.py         全文搜索
│  ├─ instance.py       单实例（Win32 互斥体 + 唤起窗口）
│  ├─ db.py / library.py  SQLite 存储
│  └─ settings.py       JSON 设置
└─ ui/                  界面
   ├─ main_window.py    无边框外壳、快捷键仲裁
   ├─ reader.py         阅读视图
   ├─ bookshelf.py      书架
   ├─ toc_panel.py      目录侧栏
   ├─ search_panel.py   搜索侧栏
   ├─ settings_dialog.py 设置面板
   ├─ eyedropper.py     全屏取色器
   ├─ toc_worker.py     目录识别后台线程
   ├─ epub_worker.py    EPUB 转换后台线程
   ├─ titlebar.py       自绘标题栏
   └─ theme.py          QSS / 图标 / 封面
```

## 文档

- [需求文档](文本浏览器-需求文档-v0.2.md)
- [技术方案与架构设计](docs/技术方案与架构设计.md)

## 已知限制

- 页码是「本次阅读第几页」，中途跳转后从 1 起算（全书页数估算待做）
- 目录识别依赖章节命名规律；对完全没有格式的 TXT 会返回空并提示
- 搜索是同步执行的（100 MB 约 35–130 ms），超大 EPUB 需移入后台线程
- EPUB 里的图片只保留 ［图片］ 占位，不渲染`n- 未做 PDF / MOBI / DOCX
