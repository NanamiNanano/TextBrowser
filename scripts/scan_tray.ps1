param([string]$Pattern = "文本浏览器")
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                     [System.Windows.Automation.Condition]::TrueCondition)
$hits = New-Object System.Collections.ArrayList
foreach ($e in $all) {
    try {
        $n = $e.Current.Name
        if ($n -and $n.Contains($Pattern)) {
            [void]$hits.Add(("{0} | {1}" -f $e.Current.ControlType.ProgrammaticName, $n))
        }
    } catch { }
}
if ($hits.Count -eq 0) { "NOT_FOUND" } else { $hits | ForEach-Object { $_ } }