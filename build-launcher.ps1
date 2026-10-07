$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Windows .NET Framework compiler not found' }
$output = Join-Path $PSScriptRoot '图片表格工作台.exe'
& $compiler /nologo /target:winexe /platform:anycpu /optimize+ /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll "/out:$output" (Join-Path $PSScriptRoot 'launcher\Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed' }
Get-FileHash -LiteralPath $output -Algorithm SHA256 | Format-List
