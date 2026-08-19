# Install HGF pre-push hook (V3.2.8)
# Points git core.hooksPath to workflow/git_hooks so the HGF gate runs before every push.
# Usage: powershell -NoProfile -File scripts/install_git_hooks.ps1
$ErrorActionPreference = "Stop"
$workflow = Split-Path -Parent $PSScriptRoot  # scripts -> workflow
$hooks = Join-Path $workflow "git_hooks"

if (-not (Test-Path $hooks)) {
    throw "hooks dir not found: $hooks"
}

git config core.hooksPath $hooks
$configured = git config core.hooksPath
Write-Host "core.hooksPath set to: $configured"
Write-Host "Install done. HGF gates run before every git push."
