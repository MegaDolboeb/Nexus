# Скачивает официальный портативный Ollama (github.com/ollama/ollama) и кладёт в packaging\ollama\,
# откуда nexus.spec вшивает его прямо в .exe — человеку не нужно ставить Ollama отдельно.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root "packaging\ollama"
$zip = Join-Path $root "packaging\ollama.zip"

$release = Invoke-RestMethod "https://api.github.com/repos/ollama/ollama/releases/latest"
$asset = $release.assets | Where-Object { $_.name -eq "ollama-windows-amd64.zip" }
Write-Host "Скачиваю $($asset.name) ($([math]::Round($asset.size/1MB,0)) МБ) из релиза $($release.tag_name)..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip

if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Expand-Archive -Path $zip -DestinationPath $dest -Force
Remove-Item $zip
Write-Host "Готово: $dest"
