# Run in the PowerShell terminal that will run terraform; do not print values.
$finshEnvPath = Join-Path $PSScriptRoot '../../.env'
if (-not (Test-Path -LiteralPath $finshEnvPath)) { throw 'finsh/.env is missing.' }
$finshKeys = @{}
foreach ($finshLine in Get-Content -LiteralPath $finshEnvPath) {
    if ($finshLine -match '^\s*(NCLOUD_ACCESS_KEY|NCLOUD_SECRET_KEY)\s*=\s*(.*)\s*$') {
        $finshValue = $Matches[2].Trim()
        if ($finshValue.Length -ge 2 -and (
            ($finshValue.StartsWith('"') -and $finshValue.EndsWith('"')) -or
            ($finshValue.StartsWith("'") -and $finshValue.EndsWith("'")))) {
            $finshValue = $finshValue.Substring(1, $finshValue.Length - 2)
        }
        $finshKeys[$Matches[1]] = $finshValue
    }
}
if (-not $finshKeys['NCLOUD_ACCESS_KEY'] -or -not $finshKeys['NCLOUD_SECRET_KEY']) {
    throw 'Both NCLOUD_ACCESS_KEY and NCLOUD_SECRET_KEY are required.'
}
$env:NCLOUD_ACCESS_KEY = $finshKeys['NCLOUD_ACCESS_KEY']
$env:NCLOUD_SECRET_KEY = $finshKeys['NCLOUD_SECRET_KEY']
$env:AWS_ACCESS_KEY_ID = $finshKeys['NCLOUD_ACCESS_KEY']
$env:AWS_SECRET_ACCESS_KEY = $finshKeys['NCLOUD_SECRET_KEY']
Write-Output 'Terraform credentials loaded (values hidden).'
