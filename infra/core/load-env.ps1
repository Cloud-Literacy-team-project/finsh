# Run in the PowerShell terminal that will execute Terraform: ./load-env.ps1
# Import only the NCP keys; do not execute .env contents or print credentials.
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot '../../.env')
)

& {
    param([string]$SourceFile)

    $credentials = @{}
    foreach ($line in (Get-Content -LiteralPath $SourceFile -ErrorAction Stop)) {
        if ($line -match '^\s*(?:export\s+)?(NCLOUD_ACCESS_KEY|NCLOUD_SECRET_KEY)\s*=\s*(.*?)\s*$') {
            $keyName = $Matches[1]
            $keyValue = $Matches[2]
            if ($keyValue.Length -ge 2 -and (
                ($keyValue.StartsWith('"') -and $keyValue.EndsWith('"')) -or
                ($keyValue.StartsWith("'") -and $keyValue.EndsWith("'"))
            )) {
                $keyValue = $keyValue.Substring(1, $keyValue.Length - 2)
            } else {
                $keyValue = ($keyValue -replace '\s+#.*$', '').Trim()
            }
            $credentials[$keyName] = $keyValue
        }
    }

    foreach ($keyName in @('NCLOUD_ACCESS_KEY', 'NCLOUD_SECRET_KEY')) {
        if ([string]::IsNullOrWhiteSpace($credentials[$keyName])) {
            throw "Missing or empty $keyName in .env."
        }
    }

    # Provider authentication.
    $env:NCLOUD_ACCESS_KEY = $credentials['NCLOUD_ACCESS_KEY']
    $env:NCLOUD_SECRET_KEY = $credentials['NCLOUD_SECRET_KEY']

    # Backend authentication uses the same NCP keys under the S3 variable names.
    $env:AWS_ACCESS_KEY_ID = $credentials['NCLOUD_ACCESS_KEY']
    $env:AWS_SECRET_ACCESS_KEY = $credentials['NCLOUD_SECRET_KEY']
    Write-Output 'NCP Provider and Object Storage Backend credentials loaded into this PowerShell process.'
} $EnvFile
