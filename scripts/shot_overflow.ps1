param([string]$Out = "tray_overflow.png")

# 打开任务栏的「显示隐藏的图标」弹出层，并截图，用来确认托盘图标在不在溢出区里。
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class W32 {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr FindWindowW(string cls, string title);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@

$root = [System.Windows.Automation.AutomationElement]::RootElement
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                     [System.Windows.Automation.Condition]::TrueCondition)
$chev = $null
foreach ($e in $all) {
    try {
        $n = $e.Current.Name
        if ($n -and ($n -like '*显示隐藏*' -or $n -like '*Show hidden*' -or $n -like '*通知*')) {
            $chev = $e; break
        }
    } catch { }
}
if ($chev) {
    Write-Host ("找到按钮: " + $chev.Current.Name)
    try {
        $p = $chev.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $p.Invoke()
        Write-Host "已点击"
    } catch { Write-Host ("Invoke 失败: " + $_.Exception.Message) }
} else {
    Write-Host "没找到溢出区按钮"
}
Start-Sleep -Milliseconds 900

$h = [W32]::FindWindowW("NotifyIconOverflowWindow", $null)
Write-Host ("溢出窗口: " + $h + " 可见=" + [W32]::IsWindowVisible($h))
$r = New-Object W32+RECT
if ([W32]::GetWindowRect($h, [ref]$r)) {
    $w = $r.Right - $r.Left; $ht = $r.Bottom - $r.Top
    Write-Host ("rect=($($r.Left),$($r.Top)) ${w}x${ht}")
    if ($w -gt 10 -and $ht -gt 10) {
        $bmp = New-Object System.Drawing.Bitmap($w, $ht)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($r.Left, $r.Top, 0, 0, (New-Object System.Drawing.Size($w, $ht)))
        $g.Dispose()
        $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        Write-Host ("已保存 " + $Out)
    }
}
