$ErrorActionPreference = "Continue"

$ProjectRoot = "G:\local_macro_portfolio_ai\local_macro_portfolio_ai"
$CondaHook = "E:\software\miniConda\shell\condabin\conda-hook.ps1"
$CondaEnv = "portfolio_ai"
$DateStamp = Get-Date -Format "yyyy-MM-dd"
$LogDir = Join-Path $ProjectRoot "outputs\logs"
$LogPath = Join-Path $LogDir "update_daily_report_$DateStamp.log"
$ArchivePath = Join-Path $ProjectRoot "outputs\archive\$DateStamp"

$HadFailure = $false
$FailedSteps = @()
$StepResults = @()

function Write-LogLine {
    param([string]$Message)

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogPath -Value "[$timestamp] $Message" -Encoding UTF8
}

function Write-CommandOutput {
    param([object[]]$Output)

    if ($null -eq $Output) {
        return
    }

    foreach ($item in $Output) {
        if ($null -eq $item) {
            continue
        }
        $text = ($item | Out-String).TrimEnd()
        if ($text.Length -gt 0) {
            Add-Content -LiteralPath $LogPath -Value $text -Encoding UTF8
        }
    }
}

function Add-Failure {
    param(
        [string]$StepName,
        [string]$Message
    )

    $script:HadFailure = $true
    $script:FailedSteps += $StepName
    Write-LogLine "ERROR: $Message"
}

function Invoke-PythonStep {
    param(
        [string]$Name,
        [string]$ScriptPath
    )

    Write-LogLine "START ${Name}: python $ScriptPath"
    $global:LASTEXITCODE = 0
    $output = & python $ScriptPath 2>&1
    $commandSucceeded = $?
    Write-CommandOutput $output
    $exitCode = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } elseif ($commandSucceeded) { 0 } else { 1 }

    $script:StepResults += [PSCustomObject]@{
        name = $Name
        script = $ScriptPath
        exit_code = $exitCode
    }

    if ($exitCode -ne 0) {
        Add-Failure $Name "$Name failed with exit code $exitCode."
    } else {
        Write-LogLine "OK $Name"
    }
    Write-LogLine "END $Name"
}

Set-Location -LiteralPath $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-LogLine "============================================================"
Write-LogLine "Daily deterministic update started."
Write-LogLine "Project root: $ProjectRoot"
Write-LogLine "Log path: $LogPath"
Write-LogLine "Archive path: $ArchivePath"

Write-LogLine "Loading Conda hook: $CondaHook"
if (Test-Path -LiteralPath $CondaHook) {
    $hookOutput = & $CondaHook 2>&1
    $hookSucceeded = $?
    Write-CommandOutput $hookOutput
    if (-not $hookSucceeded) {
        Add-Failure "conda_hook" "Failed to load Conda hook."
    }
} else {
    Add-Failure "conda_hook" "Conda hook file not found: $CondaHook"
}

Write-LogLine "Activating Conda environment: $CondaEnv"
$activateOutput = conda activate $CondaEnv 2>&1
$activateSucceeded = $?
Write-CommandOutput $activateOutput
if (-not $activateSucceeded) {
    Add-Failure "conda_activate" "Failed to activate Conda environment: $CondaEnv"
}

$PipelineSteps = @(
    @{ Name = "portfolio_check"; Script = "scripts/run_portfolio_check.py" },
    @{ Name = "market_data_check"; Script = "scripts/run_market_data_check.py" },
    @{ Name = "market_temperature_check"; Script = "scripts/run_market_temperature_check.py" },
    @{ Name = "daily_report"; Script = "scripts/run_daily_report.py" },
    @{ Name = "market_history_check"; Script = "scripts/run_market_history_check.py" },
    @{ Name = "macro_regime_history_check"; Script = "scripts/run_macro_regime_history_check.py" },
    @{ Name = "llm_context_pack"; Script = "scripts/run_llm_context_pack.py" },
    @{ Name = "archive_reports"; Script = "scripts/archive_reports.py" }
)

foreach ($step in $PipelineSteps) {
    Invoke-PythonStep -Name $step.Name -ScriptPath $step.Script
}

$status = if ($HadFailure) { "failed" } else { "success" }
$summary = @{
    status = $status
    log_path = $LogPath
    archive_path = $ArchivePath
    failed_steps = @($FailedSteps)
    step_results = @($StepResults)
    retention_policy = @{
        logs_retention_days = 30
        archive_retention_days = 365
        market_raw_cache_retention_days = 30
        enforcement = "not_implemented"
    }
}
$summaryJson = $summary | ConvertTo-Json -Depth 6

Write-LogLine "Daily deterministic update finished with status: $status"
Add-Content -LiteralPath $LogPath -Value $summaryJson -Encoding UTF8
Write-Output $summaryJson

if ($HadFailure) {
    exit 1
}
exit 0
