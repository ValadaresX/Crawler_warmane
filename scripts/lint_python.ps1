Param(
    [string[]]$Paths = @("tests", "tui_rs/check_tui_health.py")
)

$ErrorActionPreference = "Stop"

python -m ruff check @Paths
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ty check @Paths
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
