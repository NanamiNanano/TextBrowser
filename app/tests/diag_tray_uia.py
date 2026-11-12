# -*- coding: utf-8 -*-
"""用 UI Automation 检测任务栏通知区域里有没有我们的托盘图标。

托盘图标的 UIA 名称就是它的 tooltip（我们设的是「文本浏览器 —— 双击显示窗口」），
所以在整个桌面树里搜含「文本浏览器」的可访问元素即可判断图标是否真的注册了。

用法: python -m app.tests.diag_tray_uia
"""
import subprocess
import sys
import time

try:
    import comtypes.client  # noqa: F401
except ImportError:
    comtypes = None

try:
    import uiautomation  # noqa: F401
except ImportError:
    uiautomation = None

print("comtypes:", "有" if comtypes else "无")
print("uiautomation:", "有" if uiautomation else "无")

# 没有第三方 UIA 库时，退回到 PowerShell + .NET UIAutomationClient
PS = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::IsOffscreenProperty, $false)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$hits = @()
foreach ($e in $all) {
    try {
        $n = $e.Current.Name
        if ($n -and $n -like '*文本浏览器*') {
            $hits += ('{0} | {1}' -f $e.Current.ControlType.ProgrammaticName, $n)
        }
    } catch {}
}
if ($hits.Count -eq 0) { 'NOT_FOUND' } else { $hits -join "`n" }
"""


def scan(label):
    print("\n=== 扫描（%s）===" % label)
    t0 = time.time()
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", PS],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    print(out or "(无输出)")
    if r.returncode != 0:
        print("stderr:", (r.stderr or "")[:300])
    print("耗时 %.1fs" % (time.time() - t0))
    return out


if __name__ == "__main__":
    scan("当前状态")
