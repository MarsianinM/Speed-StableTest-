# Збірка портативної папки SpetTest (PyInstaller --onedir).
# Запуск з кореня репозиторію або з scripts/:
#   .\scripts\build.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== SpetTest build (onedir) ===" -ForegroundColor Cyan
Write-Host "Root: $Root"

# Заборона onefile — лише onedir (не розпаковувати в %TEMP%).
$OneFile = $false
if ($OneFile) {
    throw "Режим --onefile заборонений ТЗ. Використовуйте тільки --onedir."
}

Write-Host "Встановлення залежностей збірки…"
python -m pip install -q -e .
python -m pip install -q "pyinstaller>=6.0.0" "requests>=2.31.0"

$DistRoot = Join-Path $Root "dist"
$DistDir = Join-Path $DistRoot "SpetTest"
$BuildDir = Join-Path $Root "build"
$Entry = Join-Path $Root "scripts\entry.py"
$AppName = "SpetTest"

# Якщо попередня папка заблокована (Провідник / антивірус) — збираємо в тимчасове ім’я.
if (Test-Path $DistDir) {
    try {
        Rename-Item -LiteralPath $DistDir -NewName ("SpetTest_old_" + (Get-Date -Format "HHmmss")) -ErrorAction Stop
    } catch {
        Write-Host "Попередження: dist\SpetTest зайнятий — збираю в dist\SpetTest_new" -ForegroundColor Yellow
        Write-Host "Закрийте Провідник на цій папці і перейменуйте вручну після збірки." -ForegroundColor Yellow
        $AppName = "SpetTest_new"
        $DistDir = Join-Path $DistRoot $AppName
    }
}

Write-Host "PyInstaller…"
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name $AppName `
    --paths (Join-Path $Root "src") `
    --distpath $DistRoot `
    --workpath $BuildDir `
    --specpath $BuildDir `
    --hidden-import "spettest" `
    --hidden-import "spettest.speed" `
    --hidden-import "spettest.stable" `
    --hidden-import "spettest.report" `
    --hidden-import "spettest.errors" `
    --collect-all "certifi" `
    $Entry

$ExeName = "$AppName.exe"
if (-not (Test-Path (Join-Path $DistDir $ExeName))) {
    throw "Збірка не створила $DistDir\$ExeName"
}

# Уніфікуємо ім’я exe для ярликів (завжди SpetTest.exe).
if ($AppName -ne "SpetTest") {
    $builtExe = Join-Path $DistDir $ExeName
    $targetExe = Join-Path $DistDir "SpetTest.exe"
    if (Test-Path $builtExe) {
        Move-Item -LiteralPath $builtExe -Destination $targetExe -Force
    }
}

Write-Host "Копіювання portable ярликів і README…"
$Portable = Join-Path $Root "portable"
Copy-Item -Path (Join-Path $Portable "*") -Destination $DistDir -Force

Write-Host ""
Write-Host "Готово: $DistDir" -ForegroundColor Green
Write-Host "  SpetTest.exe"
Get-ChildItem -Path $DistDir -Filter "*.cmd" | ForEach-Object { Write-Host "  $($_.Name)" }
Write-Host "  README.txt"
Write-Host ""
Write-Host "Скопіюйте всю цю папку на флешку."
