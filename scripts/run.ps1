# 启动文本浏览器（开发模式）
# 用法: .\scripts\run.ps1 [要打开的文件]
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$py = 'C:\Users\lenovo\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = "$root;$root\vendor\py312"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root
& $py -m app @args
