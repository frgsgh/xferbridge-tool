# Merge .b64 part files and decode them back into jars.
# Usage:  powershell -ExecutionPolicy Bypass -File .\merge_and_decode.ps1
# Outputs gradle-wrapper.jar and xferbridge-1.0.0.jar next to this script.
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
if (-not $here) { $here = (Get-Location).Path }

function Merge-Decode([string]$baseName, [string]$outName) {
    $parts = Get-ChildItem -Path $here -Filter "$baseName.part*" |
        Sort-Object { [int]([regex]::Match($_.Name, '\.part(\d+)$').Groups[1].Value) }
    if ($parts.Count -eq 0) { throw "No parts found for $baseName in $here" }
    $sb = New-Object System.Text.StringBuilder
    foreach ($p in $parts) {
        [void]$sb.Append([IO.File]::ReadAllText($p.FullName))
    }
    $clean = $sb.ToString() -replace '\s', ''
    $bytes = [Convert]::FromBase64String($clean)
    $out = Join-Path $here $outName
    [IO.File]::WriteAllBytes($out, $bytes)
    $sha = [BitConverter]::ToString((New-Object Security.Cryptography.SHA1CryptoServiceProvider).ComputeHash($bytes)) -replace '-', ''
    Write-Host "Decoded $outName -> $($bytes.Length) bytes, SHA1 $sha"
}

Merge-Decode 'wrapper.jar.b64' 'gradle-wrapper.jar'
Merge-Decode 'xferbridge.jar.b64' 'xferbridge-1.0.0.jar'
Write-Host 'Done. Move the jars to their proper locations:'
Write-Host '  gradle-wrapper.jar      -> mod/gradle/wrapper/gradle-wrapper.jar'
Write-Host '  xferbridge-1.0.0.jar    -> mod/build/libs/xferbridge-1.0.0.jar'
