# 打包成免安装 exe（PyInstaller onedir）
#
# 用法:
#   .\scripts\build.ps1              打包并裁剪体积
#   .\scripts\build.ps1 -NoTrim      不裁剪（排查问题时用）
#   .\scripts\build.ps1 -OneFile     打成单文件（启动会慢一些）
#
# 产物: dist\文本浏览器\文本浏览器.exe

param(
    [switch]$OneFile,
    [switch]$NoTrim
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$root;$root\vendor\py312"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root

$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { throw '找不到 python' }

Write-Host "== PyInstaller ==" -ForegroundColor Cyan
& python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 不可用，先跑 scripts\bootstrap.ps1' }

# 裁掉用不到的 Qt 模块。PySide6-Essentials 会把整个 Qt 运行时带进来，
# 而我们只用 QtCore / QtGui / QtWidgets。
$excludes = @(
    'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
    'PySide6.QtQuickControls2', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtXml',
    'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
    'PySide6.QtPrintSupport', 'PySide6.QtDBus', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
    'PySide6.QtPositioning', 'PySide6.QtSerialPort', 'PySide6.QtWebSockets',
    'PySide6.QtWebChannel', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools', 'PySide6.QtConcurrent',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtPdf',
    'PySide6.QtPdfWidgets', 'PySide6.QtSensors', 'PySide6.QtSpatialAudio',
    'PySide6.QtStateMachine', 'PySide6.QtTextToSpeech', 'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets', 'tkinter', 'numpy', 'pandas', 'PIL', 'matplotlib',
    'scipy', 'IPython', 'pytest'
)
$excludeArgs = $excludes | ForEach-Object { @('--exclude-module', $_) }

$distDir = Join-Path $root 'dist'

$args = @(
    '-m', 'PyInstaller',
    '--noconfirm', '--clean',
    '--windowed',                                        # 不弹控制台
    '--name', 'TextBrowser',                             # 先起 ASCII 名，稍后改中文
    '--icon', (Join-Path $root 'assets\app.ico'),
    '--distpath', $distDir,
    '--workpath', (Join-Path $root 'build\pyi'),
    '--specpath', (Join-Path $root 'build'),
    '--add-data', ((Join-Path $root 'assets') + ';assets')
) + $excludeArgs

if ($OneFile) { $args += '--onefile' }
$args += (Join-Path $root 'launcher.py')

Write-Host "`n== 开始打包（首次约 1 分钟）==" -ForegroundColor Cyan
& python @args
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败，退出码 $LASTEXITCODE" }

$outDir = Join-Path $distDir 'TextBrowser'
$exeAscii = Join-Path $outDir 'TextBrowser.exe'
if (-not (Test-Path $exeAscii)) { throw "没有生成 $exeAscii" }

# ---- 裁剪：这些文件运行时用不到，删掉能省约 31 MB ----
if (-not $NoTrim) {
    $internal = Join-Path $outDir '_internal'
    $trim = @(
        # 软件 OpenGL 渲染器（19.7 MB）：QWidget 走光栅渲染，用不到
        'PySide6\opengl32sw.dll',
        # 网络与 TLS：单实例已改用 Win32 具名互斥体，不发任何网络请求
        'Qt6Network.dll', 'libcrypto-3.dll', 'libssl-3.dll',
        # SVG 与 Direct2D 后端：只用 qwindows
        'Qt6Svg.dll', 'PySide6\plugins\platforms\qdirect2d.dll',
        'PySide6\plugins\imageformats\qsvg.dll',
        # 用不到的图片格式（保留 qico / qjpeg）
        'PySide6\plugins\imageformats\qtiff.dll', 'PySide6\plugins\imageformats\qwebp.dll',
        'PySide6\plugins\imageformats\qicns.dll', 'PySide6\plugins\imageformats\qtga.dll',
        'PySide6\plugins\imageformats\qwbmp.dll', 'PySide6\plugins\imageformats\qgif.dll',
        # 打包工具链带进来的运行时垃圾
        'pyreadline3-3.5.6.dist-info', 'win32', 'pywin32_system32', 'charset_normalizer',
        '81d243bd2c585b0f4821__mypyc.cp312-win_amd64.pyd'
    )
    $removed = 0
    foreach ($rel in $trim) {
        $p = Join-Path $internal $rel
        if (Test-Path $p) {
            Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
            $removed++
        }
    }
    Write-Host "裁剪 $removed 项" -ForegroundColor DarkGray
}

# ---- 改成中文名（用户看到的是 exe 名）----
$exe = Join-Path $outDir '文本浏览器.exe'
Move-Item $exeAscii $exe -Force

$size = (Get-ChildItem $outDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host "`n== 完成 ==" -ForegroundColor Green
Write-Host ("exe      : {0}" -f $exe)
Write-Host ("目录体积 : {0:N1} MB" -f $size)
Write-Host "`n首次运行会创建数据目录：%APPDATA%\TextBrowser"
