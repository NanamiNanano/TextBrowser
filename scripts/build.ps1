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

# 先打到临时目录：dist 里的旧文件可能被正在运行的程序（或残留句柄）锁住，
# 直接让 PyInstaller 输出到 dist 会整条失败。打完再同步过去。
$tmpDist = Join-Path $root 'build\dist_tmp'

$args = @(
    '-m', 'PyInstaller',
    '--noconfirm', '--clean',
    '--windowed',                                        # 不弹控制台
    '--name', 'TextBrowser',                             # 先起 ASCII 名，稍后改中文
    '--icon', (Join-Path $root 'assets\app.ico'),
    '--distpath', $tmpDist,
    '--workpath', (Join-Path $root 'build\pyi'),
    '--specpath', (Join-Path $root 'build'),
    '--add-data', ((Join-Path $root 'assets') + ';assets')
) + $excludeArgs

if ($OneFile) { $args += '--onefile' }
$args += (Join-Path $root 'launcher.py')

Write-Host "`n== 开始打包（首次约 1 分钟）==" -ForegroundColor Cyan
& python @args
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败，退出码 $LASTEXITCODE" }

# ---- 同步到 dist ----
$buildDir = Join-Path $tmpDist 'TextBrowser'
if (-not (Test-Path $buildDir)) { throw "没有生成 $buildDir" }

$targetDir = Join-Path $distDir "TextBrowser"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
$srcSize = (Get-ChildItem $buildDir -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("同步到 {0} ..." -f $targetDir) -ForegroundColor DarkGray
# /MIR 镜像；/R:1 /W:1 遇到被占用的文件快速跳过，不卡住
& robocopy $buildDir $targetDir /MIR /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
# robocopy 退出码是位组合：1=复制了文件 2=发现多余项 4=不匹配 8=有项目没复制成 16=严重错误。
# 8 通常是「dist 里有个被占用的旧日志文件删不掉」，不影响程序本体，继续。
if ($LASTEXITCODE -ge 16) { throw "robocopy 同步失败，退出码 $LASTEXITCODE" }
if ($LASTEXITCODE -band 8) {
    Write-Host "提示：dist 里有旧文件被占用，未能删除（通常是 launcher.log），不影响使用" -ForegroundColor Yellow
}

# 记录失败的项（被占用的文件不会同步成功）
$dstSize = (Get-ChildItem $targetDir -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object Length -Sum).Sum
if ($dstSize -lt $srcSize * 0.98) {
    Write-Host "警告：dist 体积明显小于临时目录，可能有文件被占用未覆盖" -ForegroundColor Yellow
    Write-Host "      关闭正在运行的程序后重跑本脚本即可" -ForegroundColor Yellow
}

$outDir = $targetDir
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
[IO.File]::Copy($exeAscii, $exe, $true)
Remove-Item $exeAscii -Force -ErrorAction SilentlyContinue

$size = (Get-ChildItem $outDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host "`n== 完成 ==" -ForegroundColor Green
Write-Host ("exe      : {0}" -f $exe)
Write-Host ("目录体积 : {0:N1} MB" -f $size)
Write-Host "`n首次运行会创建数据目录：%APPDATA%\TextBrowser"
