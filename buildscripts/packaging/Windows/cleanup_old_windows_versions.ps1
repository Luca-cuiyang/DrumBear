# HARD RELEASE POLICY:
# Keep only the current DB绘谱 MSI packages.

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
$productName = "DB" + [char]0x7ED8 + [char]0x8C31
$patterns = @(
    "*DB*Score*.msi",
    "*DB*Score*.exe",
    "*DB*Score*.win",
    "*DB*Score*.zip",
    "*DB*Score*.7z",
    "*DB*Score*.appx",
    "*DB*Score*.msix",
    "*$productName*.msi",
    "*$productName*.exe",
    "*$productName*.win",
    "*$productName*.zip",
    "*$productName*.7z",
    "*$productName*.appx",
    "*$productName*.msix"
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
    Write-Output "No DB绘谱 Windows package candidates found."
    exit 0
}

$publicMsiName = "$productName-Windows-$Version.msi"
$keepPaths = @(
    [IO.Path]::GetFullPath((Join-Path "C:\Mac\Home\Desktop" $publicMsiName))
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
