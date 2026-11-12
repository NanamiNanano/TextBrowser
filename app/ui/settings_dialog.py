# -*- coding: utf-8 -*-
"""设置面板（无边框对话框，改动即时生效）。

设计要点：
  * 所有控件改动后立刻 emit sig_changed，主窗口负责“应用到界面 + 存盘”，
    不做「确定/取消」——阅读器的外观调整需要边调边看。
  * 取色不自己做，只发 sig_pick_screen，由主窗口弹全屏取色器再回填，
    因为遮罩需要覆盖整个屏幕，不能是对话框的子控件。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox,
                               QDoubleSpinBox, QFontComboBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QVBoxLayout,
                               QWidget)

from ..core.settings import PRESETS, Settings
from .theme import mix


class ColorButton(QPushButton):
    """显示色块 + 十六进制值，点击打开调色板。"""

    color_picked = Signal(str)

    def __init__(self, color: str, title: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._title = title
        self.setFixedSize(96, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._choose)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self._color = color
        c = QColor(color)
        fg = "#111111" if c.lightnessF() > 0.55 else "#FFFFFF"
        self.setText(color.upper())
        self.setStyleSheet(
            "QPushButton { background: %s; color: %s; border: 1px solid %s;"
            " border-radius: 6px; font-size: 11px; }"
            % (color, fg, mix(color, "#000000", 0.25)))

    def _choose(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, self._title)
        if c.isValid():
            self.set_color(c.name())
            self.color_picked.emit(c.name())


class SettingsDialog(QWidget):
    sig_changed = Signal()          # 任一设置变化
    sig_pick_screen = Signal()      # 请求从屏幕取色（背景色）
    sig_close = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("SettingsDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedSize(720, 600)
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 标题 ----
        head = QWidget()
        head.setObjectName("TocHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 14, 12, 10)
        title = QLabel("设置")
        title.setObjectName("SectionTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        btn_close = QPushButton("×")
        btn_close.setObjectName("TocClose")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.sig_close)
        hl.addWidget(btn_close)
        root.addWidget(head)

        # ---- 内容 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 4, 20, 16)
        bl.setSpacing(14)

        bl.addWidget(self._build_presets())
        bl.addWidget(self._build_colors())
        bl.addWidget(self._build_typography())
        bl.addWidget(self._build_layout())
        bl.addWidget(self._build_reading())
        bl.addWidget(self._build_window())
        bl.addStretch(1)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ---- 底部 ----
        foot = QWidget()
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(20, 8, 20, 14)
        btn_reset = QPushButton("恢复默认")
        btn_reset.clicked.connect(self._reset)
        fl.addWidget(btn_reset)
        fl.addStretch(1)
        btn_ok = QPushButton("完成")
        btn_ok.setObjectName("Primary")
        btn_ok.clicked.connect(self.sig_close)
        fl.addWidget(btn_ok)
        root.addWidget(foot)

        self.refresh()

    # ------------------------------------------------------------ 分组
    @staticmethod
    def _group(title: str) -> tuple:
        box = QFrame()
        box.setObjectName("SettingsGroup")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(8)
        lbl = QLabel(title)
        lbl.setObjectName("SettingsGroupTitle")
        lay.addWidget(lbl)
        return box, lay

    def _build_presets(self):
        box, lay = self._group("预设主题")
        row = QHBoxLayout()
        row.setSpacing(10)
        for p in PRESETS:
            btn = QPushButton(p["name"])
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: %s; color: %s; border: 1px solid %s;"
                " border-radius: 8px; font-size: 12px; }"
                "QPushButton:hover { border-color: %s; }"
                % (p["bg"], p["fg"], mix(p["bg"], p["fg"], 0.35),
                   mix(p["bg"], p["fg"], 0.7)))
            btn.clicked.connect(lambda _=False, q=p: self._apply_preset(q))
            row.addWidget(btn)
        lay.addLayout(row)
        return box

    def _build_colors(self):
        box, lay = self._group("颜色")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel("背景色"), 0, 0)
        self.btn_bg = ColorButton(self.settings.get("appearance.bgColor"), "背景色")
        self.btn_bg.color_picked.connect(lambda c: self._set("appearance.bgColor", c))
        grid.addWidget(self.btn_bg, 0, 1)

        btn_pick = QPushButton("从屏幕取色")
        btn_pick.setToolTip("把鼠标移到屏幕任意位置，点击即可吸取该处颜色作为背景")
        btn_pick.clicked.connect(self.sig_pick_screen)
        grid.addWidget(btn_pick, 0, 2)

        grid.addWidget(QLabel("文字色"), 1, 0)
        self.btn_fg = ColorButton(self.settings.get("appearance.textColor"), "文字色")
        self.btn_fg.color_picked.connect(lambda c: self._set("appearance.textColor", c))
        grid.addWidget(self.btn_fg, 1, 1)

        self.lbl_contrast = QLabel("")
        self.lbl_contrast.setObjectName("Muted")
        grid.addWidget(self.lbl_contrast, 1, 2)
        lay.addLayout(grid)
        return box

    def _build_typography(self):
        box, lay = self._group("字体与排版")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel("字体"), 0, 0)
        self.cmb_font = QFontComboBox()
        self.cmb_font.setMinimumWidth(240)
        self.cmb_font.currentFontChanged.connect(self._on_font)
        grid.addWidget(self.cmb_font, 0, 1, 1, 2)

        grid.addWidget(QLabel("字号"), 1, 0)
        self.spn_size = QSpinBox()
        self.spn_size.setRange(12, 72)
        self.spn_size.setSuffix(" px")
        self.spn_size.valueChanged.connect(
            lambda v: self._set("appearance.fontSize", int(v)))
        grid.addWidget(self.spn_size, 1, 1)

        grid.addWidget(QLabel("行距"), 2, 0)
        self.spn_line = QDoubleSpinBox()
        self.spn_line.setRange(1.0, 2.5)
        self.spn_line.setSingleStep(0.1)
        self.spn_line.setDecimals(1)
        self.spn_line.valueChanged.connect(
            lambda v: self._set("appearance.lineHeight", round(float(v), 2)))
        grid.addWidget(self.spn_line, 2, 1)

        grid.addWidget(QLabel("字间距"), 3, 0)
        self.spn_spacing = QDoubleSpinBox()
        self.spn_spacing.setRange(-2.0, 8.0)
        self.spn_spacing.setSingleStep(0.5)
        self.spn_spacing.setDecimals(1)
        self.spn_spacing.setSuffix(" px")
        self.spn_spacing.valueChanged.connect(
            lambda v: self._set("appearance.letterSpacing", round(float(v), 2)))
        grid.addWidget(self.spn_spacing, 3, 1)

        grid.addWidget(QLabel("对齐"), 4, 0)
        self.cmb_align = QComboBox()
        self.cmb_align.addItem("左对齐", "left")
        self.cmb_align.addItem("两端对齐", "justify")
        self.cmb_align.currentIndexChanged.connect(
            lambda _i: self._set("appearance.align", self.cmb_align.currentData()))
        grid.addWidget(self.cmb_align, 4, 1)

        grid.addWidget(QLabel("首行缩进"), 5, 0)
        self.cmb_indent = QComboBox()
        self.cmb_indent.addItem("不缩进", 0.0)
        self.cmb_indent.addItem("缩进 2 字符", 2.0)
        self.cmb_indent.currentIndexChanged.connect(
            lambda _i: self._set("appearance.textIndent", self.cmb_indent.currentData()))
        grid.addWidget(self.cmb_indent, 5, 1)
        lay.addLayout(grid)
        return box

    def _build_layout(self):
        box, lay = self._group("版面")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel("左右边距"), 0, 0)
        self.spn_mh = QSpinBox()
        self.spn_mh.setRange(0, 200)
        self.spn_mh.setSuffix(" px")
        self.spn_mh.valueChanged.connect(
            lambda v: self._set("appearance.marginH", int(v)))
        grid.addWidget(self.spn_mh, 0, 1)

        grid.addWidget(QLabel("上下边距"), 1, 0)
        self.spn_mv = QSpinBox()
        self.spn_mv.setRange(0, 160)
        self.spn_mv.setSuffix(" px")
        self.spn_mv.valueChanged.connect(
            lambda v: self._set("appearance.marginV", int(v)))
        grid.addWidget(self.spn_mv, 1, 1)

        grid.addWidget(QLabel("正文最大宽度"), 2, 0)
        self.spn_width = QSpinBox()
        self.spn_width.setRange(420, 1600)
        self.spn_width.setSingleStep(20)
        self.spn_width.setSuffix(" px")
        self.spn_width.valueChanged.connect(
            lambda v: self._set("appearance.maxContentWidth", int(v)))
        grid.addWidget(self.spn_width, 2, 1)
        lay.addLayout(grid)
        return box

    def _build_reading(self):
        box, lay = self._group("阅读")
        row = QHBoxLayout()
        row.addWidget(QLabel("模式"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("分页", "paginate")
        self.cmb_mode.addItem("连续滚动", "scroll")
        self.cmb_mode.currentIndexChanged.connect(self._on_mode)
        row.addWidget(self.cmb_mode)
        row.addStretch(1)
        lay.addLayout(row)

        self.chk_footer = QCheckBox("显示页脚（章节名 / 页码 / 进度）")
        self.chk_footer.stateChanged.connect(
            lambda _s: self._set("reading.showFooter", self.chk_footer.isChecked()))
        lay.addWidget(self.chk_footer)
        return box

    def _build_window(self):
        box, lay = self._group("窗口")
        row = QHBoxLayout()
        row.addWidget(QLabel("背景不透明度"))
        self.sld_opacity = QSlider(Qt.Orientation.Horizontal)
        self.sld_opacity.setRange(0, 100)
        self.sld_opacity.setToolTip("只让背景透明，文字始终不透明")
        self.sld_opacity.setFixedWidth(220)
        self.sld_opacity.valueChanged.connect(self._on_opacity)
        row.addWidget(self.sld_opacity)
        self.lbl_opacity = QLabel("100%")
        self.lbl_opacity.setObjectName("Muted")
        row.addWidget(self.lbl_opacity)
        row.addStretch(1)
        lay.addLayout(row)

        # ESC / 关闭按钮的行为。默认收进托盘；但 Windows 会把新托盘图标塞进
        # 任务栏右下角的「^」溢出区，很多人按完 ESC 就找不到程序了，
        # 所以给一个「最小化到任务栏」的选择。
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("ESC / 关闭时"))
        self.cmb_esc = QComboBox()
        self.cmb_esc.addItem("自动（托盘可用就收进托盘）", "auto")
        self.cmb_esc.addItem("最小化到任务栏（任务栏留有图标）", "minimize")
        self.cmb_esc.addItem("收进系统托盘（托盘不可用时会退化为最小化）", "tray")
        self.cmb_esc.setMinimumWidth(240)
        self.cmb_esc.currentIndexChanged.connect(
            lambda _i: self._set("window.escAction", self.cmb_esc.currentData()))
        row2.addWidget(self.cmb_esc)
        row2.addStretch(1)
        lay.addLayout(row2)
        return box

    # ------------------------------------------------------------ 应用
    def _set(self, key: str, value) -> None:
        if self._loading:
            return
        self.settings.set(key, value)
        self.settings.save()
        self.sig_changed.emit()

    def _on_font(self, qfont: QFont) -> None:
        if self._loading:
            return
        self._set("appearance.fontFamily", qfont.family())

    def _on_mode(self, _index: int) -> None:
        if self._loading:
            return
        self._set("reading.mode", self.cmb_mode.currentData())

    def _on_opacity(self, value: int) -> None:
        self.lbl_opacity.setText("%d%%" % value)
        # 低于这个值基本看不清界面，主窗口会给出一次提示
        self.lbl_opacity.setStyleSheet("color:#C0392B;" if value < 20 else "")
        if self._loading:
            return
        self._set("appearance.bgOpacity", round(value / 100.0, 2))

    def _apply_preset(self, preset: dict) -> None:
        if self._loading:
            return
        self.settings.set("appearance.bgColor", preset["bg"])
        self.settings.set("appearance.textColor", preset["fg"])
        self.settings.save()
        self.refresh()
        self.sig_changed.emit()

    def _reset(self) -> None:
        self.settings.reset()
        self.refresh()
        self.sig_changed.emit()

    # ------------------------------------------------------------ 同步显示
    def refresh(self) -> None:
        """把 settings 的当前值刷回所有控件（外部改色后也要调）。"""
        self._loading = True
        try:
            s = self.settings
            self.btn_bg.set_color(s.get("appearance.bgColor"))
            self.btn_fg.set_color(s.get("appearance.textColor"))
            f = QFont(str(s.get("appearance.fontFamily")))
            self.cmb_font.setCurrentFont(f)
            self.spn_size.setValue(int(s.get("appearance.fontSize")))
            self.spn_line.setValue(float(s.get("appearance.lineHeight")))
            self.spn_spacing.setValue(float(s.get("appearance.letterSpacing") or 0))
            idx = self.cmb_align.findData(s.get("appearance.align"))
            self.cmb_align.setCurrentIndex(max(0, idx))
            idx = self.cmb_indent.findData(float(s.get("appearance.textIndent") or 0))
            self.cmb_indent.setCurrentIndex(max(0, idx))
            self.spn_mh.setValue(int(s.get("appearance.marginH")))
            self.spn_mv.setValue(int(s.get("appearance.marginV")))
            self.spn_width.setValue(int(s.get("appearance.maxContentWidth")))
            idx = self.cmb_mode.findData(s.get("reading.mode"))
            self.cmb_mode.setCurrentIndex(max(0, idx))
            self.chk_footer.setChecked(bool(s.get("reading.showFooter", True)))
            idx = self.cmb_esc.findData(s.get("window.escAction", "auto"))
            self.cmb_esc.setCurrentIndex(max(0, idx))
            op = int(round(float(s.get("appearance.bgOpacity", 1.0)) * 100))
            self.sld_opacity.setValue(op)
            self.lbl_opacity.setText("%d%%" % op)
            self._update_contrast()
        finally:
            self._loading = False

    def _update_contrast(self) -> None:
        bg = QColor(self.settings.get("appearance.bgColor"))
        fg = QColor(self.settings.get("appearance.textColor"))

        def lum(c):
            def ch(v):
                v = v / 255.0
                return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
            return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())

        l1, l2 = lum(bg), lum(fg)
        if l1 < l2:
            l1, l2 = l2, l1
        ratio = (l1 + 0.05) / (l2 + 0.05)
        text = "对比度 %.1f:1" % ratio
        if ratio < 3.0:
            text += "（偏低，建议调整）"
        self.lbl_contrast.setText(text)

    # ------------------------------------------------------------ 窗口行为
    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.sig_close.emit()
            ev.accept()
            return
        super().keyPressEvent(ev)
