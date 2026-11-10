# 跑全部自动测试
#
# 用法: .\scripts\test.ps1 [-Verbose]

param([switch]$Verbose)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$root;$root\vendor\py312"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root

$suites = @(
    @{ name = '核心层';   module = 'app.tests.smoke_core' },
    @{ name = '目录';     module = 'app.tests.test_toc' },
    @{ name = '搜索';     module = 'app.tests.test_search' },
    @{ name = '阅读器';   module = 'app.tests.test_reader' },
    @{ name = '阅读模式'; module = 'app.tests.test_modes' },
    @{ name = '设置与取色'; module = 'app.tests.test_m3' }
)

$failed = 0
foreach ($s in $suites) {
    Write-Host "`n===== $($s.name) =====" -ForegroundColor Cyan
    & python -m $s.module 2>&1
    if ($LASTEXITCODE -ne 0) { $failed++ }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "全部通过" -ForegroundColor Green
} else {
    Write-Host "$failed 个套件失败" -ForegroundColor Red
}
exit $failed
