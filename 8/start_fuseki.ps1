param([switch]$Rdfs)

$ErrorActionPreference = "Stop"
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

$fusekiRoot = "C:\fuseki-lab8"
$fusekiHome = Join-Path $fusekiRoot "apache-jena-fuseki-5.2.0"
$config = if ($Rdfs) {
    Join-Path $fusekiRoot "fuseki-config-fin-rdfs.ttl"
} else {
    Join-Path $fusekiRoot "fuseki-config-fin.ttl"
}

if (-not (Test-Path "$fusekiHome\fuseki-server.bat")) {
    Write-Error "Не знайдено $fusekiHome. Скопіюйте tools\apache-jena-fuseki-5.2.0 у C:\fuseki-lab8\"
}

Write-Host "Java:" (java -version 2>&1 | Select-Object -First 1)
Write-Host "Config: $config"
Write-Host "UI:     http://localhost:3030/"
Write-Host "Dataset http://localhost:3030/fin/"
Set-Location $fusekiHome
& .\fuseki-server.bat --config=$config
