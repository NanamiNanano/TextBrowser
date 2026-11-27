# -*- coding: utf-8 -*-
# 自解压安装包的安装脚本。
#
# 由 install.cmd 调用（那边是纯 ASCII，避开 cmd 的代码页问题）。
# 这里负责：复制到 %LOCALAPPDATA%\TextBrowser、建桌面快捷方式、启动。
# 出错时弹一个消息框——因为安装包的控制台是隐藏的，没有可见输出。
#
# 环境变量 TB_INSTALL_SILENT=1 时不弹框，只写日志（用于自动化验证）。

$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
$dest = Join-Path $env:LOCALAPPDATA 'TextBrowser'
$exeName = '文本浏览器.exe'
$logPath = Join-Path $env:TEMP 'textbrowser_install.log'
$silent = ($env:TB_INSTALL_SILENT -eq '1')

function Write-Log($msg) {
    try { Add-Content -Path $logPath -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg) -Encoding UTF8 } catch { }
}

function Show-Error($msg) {
    Write-Log "ERROR: $msg"
    if ($silent) { return }
    try {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "$msg`n`n可以手动处理：把整个安装包解压出来的文件夹复制到任意位置，直接运行 $exeName。",
            '文本浏览器 安装未完成',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
    } catch { }
}

Write-Log "开始安装：$src -> $dest"

try {
    if (-not (Test-Path (Join-Path $src $exeName))) {
        throw "安装包里找不到 $exeName"
    }

    if (-not (Test-Path $dest)) {
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
    }

    # 复制整个程序目录（_internal 里有 Qt 运行时，必须一起拷），
    # 但安装脚本自己不用留在安装目录里
    $skip = @('install.cmd', 'install.ps1')
    Get-ChildItem -Path $src -Force | Where-Object { $skip -notcontains $_.Name } |
        ForEach-Object {
            Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
        }
    Write-Log "文件已复制"

    # 桌面快捷方式
    $target = Join-Path $dest $exeName
    if (-not (Test-Path $target)) { throw "复制后找不到 $target" }
    $ws = New-Object -ComObject WScript.Shell
    $lnkPath = Join-Path ([Environment]::GetFolderPath('Desktop')) '文本浏览器.lnk'
    $lnk = $ws.CreateShortcut($lnkPath)
    $lnk.TargetPath = $target
    $lnk.WorkingDirectory = $dest
    $lnk.IconLocation = "$target,0"
    $lnk.Description = '文本浏览器 —— TXT / EPUB 阅读'
    $lnk.Save()
    Write-Log "快捷方式已创建：$lnkPath"

    # 启动
    Start-Process -FilePath $target
    Write-Log "已启动"
    Write-Log "安装成功"
}
catch {
    Show-Error ("{0}" -f $_.Exception.Message)
    exit 1
}
exit 0
