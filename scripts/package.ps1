# 生成给「不懂电脑的用户」直接用的发行包
#
# 产出（都在 release\ 下）：
#   文本浏览器-<版本>-win64.zip     绿色版：解压 → 双击 exe
#   文本浏览器-<版本>-安装版.exe    自解压安装包：双击 → 装到 %LOCALAPPDATA%\TextBrowser → 桌面图标
#
# 用法： .\scripts\package.ps1 [-SkipBuild] [-Version 1.0]

param(
    [switch]$SkipBuild,
    [string]$Version = "1.0"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root

$distDir = Join-Path $root 'dist\TextBrowser'
$exe = Join-Path $distDir '文本浏览器.exe'
$releaseDir = Join-Path $root 'release'
$stageDir = Join-Path $root 'build\release_stage'
$pkgName = "文本浏览器-$Version-win64"

if (-not $SkipBuild) {
    Write-Host "== 先打包程序 ==" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build.ps1')
    if ($LASTEXITCODE -ne 0) { throw "build.ps1 失败" }
}
if (-not (Test-Path $exe)) { throw "找不到 $exe，先跑 build.ps1" }

# ---------------------------------------------------------------- 绿色版目录
if (Test-Path $stageDir) { Remove-Item $stageDir -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null

Write-Host "== 复制程序文件 ==" -ForegroundColor Cyan
& robocopy $distDir $stageDir /MIR /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
if ($LASTEXITCODE -ge 16) { throw "复制失败" }

Copy-Item (Join-Path $root 'packaging\使用说明.txt') $stageDir -Force
Copy-Item (Join-Path $root 'packaging\创建桌面快捷方式.cmd') $stageDir -Force

# ---------------------------------------------------------------- 绿色版 zip
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
$zip = Join-Path $releaseDir "$pkgName.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "== 生成 zip ==" -ForegroundColor Cyan
Push-Location $stageDir
& tar.exe -a -c -f $zip --exclude=launcher.log --exclude=*.log *
$tarCode = $LASTEXITCODE
Pop-Location
if ($tarCode -ge 1) { throw "tar 打包失败，退出码 $tarCode" }

# ---------------------------------------------------------------- 安装版
# iexpress / makecab 是 Windows 老工具，路径里带中文会直接失败
# （实测 makecab 报 "Could not find file"），所以整段在纯 ASCII 的 %TEMP% 里做。
Write-Host "== 准备安装包素材 ==" -ForegroundColor Cyan
$asciiWork = Join-Path $env:TEMP 'tb_sfx_build'
if (Test-Path $asciiWork) { Remove-Item $asciiWork -Recurse -Force -ErrorAction SilentlyContinue }
$sfxStage = Join-Path $asciiWork 'stage'
New-Item -ItemType Directory -Force -Path $sfxStage | Out-Null

& robocopy $stageDir $sfxStage /MIR /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
if ($LASTEXITCODE -ge 16) { throw "复制到临时目录失败" }

# 安装脚本只放进自解压包，不放绿色版（绿色版里它是多余的）
Copy-Item (Join-Path $root 'packaging\install.cmd') $sfxStage -Force
Copy-Item (Join-Path $root 'packaging\install.ps1') $sfxStage -Force
Copy-Item (Join-Path $root 'packaging\卸载.cmd') $sfxStage -Force

# 清单：target 名 -> 源文件（makecab 按 base name 平铺，不能重名）
$files = Get-ChildItem $sfxStage -Recurse -File | Where-Object { $_.Name -ne 'launcher.log' }
$fileLines = @()
for ($i = 0; $i -lt $files.Count; $i++) {
    $rel = $files[$i].FullName.Substring($sfxStage.Length).TrimStart('\')
    $fileLines += "FILE$i=$rel"
}
$srcLines = @()
for ($i = 0; $i -lt $files.Count; $i++) { $srcLines += "%FILE$i%=" }

$sfxExe = Join-Path $asciiWork 'setup.exe'
$sedPath = Join-Path $asciiWork 'sfx.sed'
$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$sfxExe
FriendlyName=TextBrowser
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[Strings]
$($fileLines -join "`r`n")
[SourceFiles]
SourceFiles0=$sfxStage\
[SourceFiles0]
$($srcLines -join "`r`n")
"@
# SED 用 ANSI(GBK) 写：iexpress 只认本地代码页
[IO.File]::WriteAllText($sedPath, $sed, [Text.Encoding]::GetEncoding(936))

Write-Host "== 生成安装包（$($files.Count) 个文件，约 1 分钟）==" -ForegroundColor Cyan
$sw = [Diagnostics.Stopwatch]::StartNew()
& iexpress.exe /N /Q $sedPath | Out-Null
Start-Sleep -Seconds 2
if (-not (Test-Path $sfxExe)) {
    throw "iexpress 没有生成安装包，检查 $sedPath"
}
$installer = Join-Path $releaseDir "文本浏览器-$Version-安装版.exe"
Copy-Item $sfxExe $installer -Force
Write-Host ("安装包 {0:N1} MB，耗时 {1:N0}s" -f ((Get-Item $installer).Length / 1MB), $sw.Elapsed.TotalSeconds)

# ---------------------------------------------------------------- 汇总
Write-Host "`n== 完成 ==" -ForegroundColor Green
Get-ChildItem $releaseDir -File | ForEach-Object {
    "  {0,-34} {1,7:N1} MB" -f $_.Name, ($_.Length / 1MB)
}
Write-Host "`n绿色版：解压 zip → 双击 文本浏览器.exe"
Write-Host "安装版：双击 exe → 装到 %LOCALAPPDATA%\TextBrowser → 桌面快捷方式 → 自动启动"
