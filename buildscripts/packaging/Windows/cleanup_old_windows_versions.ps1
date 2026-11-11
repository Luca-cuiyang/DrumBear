# HARD RELEASE POLICY:
# Keep only the current DB Score MSI packages.

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$candidateRoots = @(
    "C:\Mac\Home",
    "C:\Mac\Home\Desktop",
    "C:\Mac\Home\Downloads",
    "C:\DBscore\dist"
)
$patterns = @(
    "*DB*Score*.msi",
    "*DB*Score*.exe",
    "*DB*Score*.win",
    "*DB*Score*.zip",
    "*DB*Score*.7z",
    "*DB*Score*.appx",
    "*DB*Score*.msix"
)

$candidates = foreach ($root in $candidateRoots) {
    if (Test-Path -LiteralPath $root) {
        foreach ($pattern in $patterns) {
            Get-ChildItem -LiteralPath $root -File -Filter $pattern -ErrorAction SilentlyContinue
        }
    }
}

$candidates = $candidates | Sort-Object FullName -Unique
if (-not $candidates) {
    Write-Output "No DB Score Windows package candidates found."
    exit 0
}

$publicMsiName = "DB score" + [char]0x5236 + [char]0x8C31 + [char]0x5927 + [char]0x5E08 + ".msi"
$keepPaths = @(
    [IO.Path]::GetFullPath((Join-Path "C:\Mac\Home\Desktop" $publicMsiName)),
    [IO.Path]::GetFullPath("C:\Mac\Home\Desktop\DB-Score-Windows-$Version.msi")
)

foreach ($candidate in $candidates) {
    $candidatePath = [IO.Path]::GetFullPath($candidate.FullName)
    if ($keepPaths -contains $candidatePath) {
        Write-Output "Keeping current Windows package: $candidatePath"
        continue
    }
    Remove-Item -LiteralPath $candidatePath -Force
    Write-Output "Removed old Windows package: $candidatePath"
}
