param(
    [string]$Python = "python",
    [string]$XlsxWriterPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distPath = Join-Path $projectRoot "dist"

function Build-Executable {
    param([string]$Name, [string]$Entry, [switch]$Windowed)
    $args = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        $(if ($Windowed) { "--windowed" } else { "--console" }),
        "--name", $Name,
        "--distpath", $distPath,
        "--workpath", (Join-Path $projectRoot "build\pyinstaller\$Name"),
        "--specpath", (Join-Path $projectRoot "build"),
        "--paths", (Join-Path $projectRoot "src"),
        "--add-data", "$(Join-Path $projectRoot 'config.example.toml');.",
        "--add-data", "$(Join-Path $projectRoot 'README.md');."
    )
    if ($XlsxWriterPath) { $args += @("--paths", $XlsxWriterPath) }
    $args += (Join-Path $projectRoot $Entry)
    & $Python @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Build-Executable -Name "mcnp-report" -Entry "src\mcnp_report\__main__.py"
Build-Executable -Name "mcnp-report-gui" -Entry "gui_entry.py" -Windowed
Write-Host "Built: $(Join-Path $distPath 'mcnp-report.exe')"
Write-Host "Built: $(Join-Path $distPath 'mcnp-report-gui.exe')"
