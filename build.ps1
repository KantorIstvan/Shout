# Builds dist\Shout (the app) and ShoutSetup.exe (the installer, in the project root).
#
# Shout.exe is python.org's Authenticode-signed pythonw.exe, renamed. A PyInstaller bootloader would be
# an unsigned exe, which Smart App Control blocks with no override; the signed runtime runs everywhere.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$version = '1.0.0'
$pyver = & $py -c "import platform; print(platform.python_version())"
$dist = Join-Path $root 'dist\Shout'
$cache = Join-Path $root 'build'

if (Test-Path (Join-Path $root 'dist')) { Remove-Item -Recurse -Force (Join-Path $root 'dist') }
New-Item -ItemType Directory -Force $dist, $cache | Out-Null

# 1. Signed CPython runtime --------------------------------------------------------------------
$zip = Join-Path $cache "python-$pyver-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    curl.exe -sfL -o $zip "https://www.python.org/ftp/python/$pyver/python-$pyver-embed-amd64.zip"
    if ($LASTEXITCODE) { throw "Python $pyver embeddable download failed" }
}
Expand-Archive $zip $dist
foreach ($exe in 'python.exe', 'pythonw.exe') {
    $sig = Get-AuthenticodeSignature (Join-Path $dist $exe)
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw "$exe is not signed by the Python Software Foundation"
    }
}
Move-Item (Join-Path $dist 'pythonw.exe') (Join-Path $dist 'Shout.exe')
Remove-Item (Join-Path $dist 'python.exe')
$pth = Get-ChildItem $dist -Filter 'python*._pth' | Select-Object -First 1
Set-Content $pth.FullName "$($pth.BaseName).zip`r`n.`r`napp`r`nLib\site-packages`r`nimport site" -Encoding ascii

# 2. Dependencies (same wheels as the dev venv, so Smart App Control sees files with known reputation) ---
$site = Join-Path $dist 'Lib\site-packages'
& $py -m pip install --quiet --disable-pip-version-check --no-deps --no-compile --target $site -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE) { throw 'pip install failed' }
# console-script launchers are unsigned exes we never use; Qt tools, QML and software OpenGL are unused by a widgets app
$prune = @('bin', 'PySide6\qml', 'PySide6\translations', 'PySide6\include', 'PySide6\typesystems', 'PySide6\glue',
           'PySide6\scripts', 'PySide6\examples', 'PySide6\opengl32sw.dll', 'PySide6\*.exe',
           'PySide6\Qt6Quick*.dll', 'PySide6\Qt6Qml*.dll', 'PySide6\Qt6Designer*.dll', 'PySide6\Qt6OpenGL*.dll',
           'PySide6\QtQuick*.pyd', 'PySide6\QtQml*.pyd', 'PySide6\QtDesigner*.pyd', 'PySide6\QtOpenGL*.pyd',
           'PySide6\QtSql*.pyd', 'PySide6\Qt6Sql*.dll', 'PySide6\QtTest*.pyd', 'PySide6\Qt6Test*.dll',
           'PySide6\QtConcurrent*.pyd', 'PySide6\Qt6Concurrent*.dll', 'PySide6\QtHelp*.pyd', 'PySide6\Qt6Help*.dll',
           'PySide6\QtUiTools*.pyd', 'PySide6\Qt6UiTools*.dll', 'PySide6\QtXml*.pyd', 'PySide6\Qt6Xml*.dll',
           'PySide6\QtDBus*.pyd', 'PySide6\Qt6DBus*.dll', 'PySide6\QtPrintSupport*.pyd', 'PySide6\Qt6PrintSupport*.dll',
           'PySide6\plugins\sqldrivers', 'PySide6\plugins\qmltooling', 'PySide6\plugins\designer',
           'PySide6\plugins\generic', 'PySide6\plugins\networkinformation', 'PySide6\plugins\platforminputcontexts',
           # onnxruntime only runs the Silero VAD model here; its dev tools nest deep enough to hit MAX_PATH
           'onnxruntime\tools', 'onnxruntime\transformers', 'onnxruntime\quantization')
foreach ($p in $prune) { Get-Item (Join-Path $site $p) -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force }
Get-ChildItem $site -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Set-Content (Join-Path $site 'shout_boot.pth') 'import shout_boot' -Encoding ascii

# 3. App sources and assets ----------------------------------------------------------------------
$app = Join-Path $dist 'app'
New-Item -ItemType Directory -Force $app | Out-Null
Copy-Item (Join-Path $root '*.py') $app -Exclude 'test_*.py', 'make_icon.py'
Copy-Item -Recurse (Join-Path $root 'assets') $app
& $py -m compileall -q $app $site | Out-Null

$size = (Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("dist\Shout: {0:N0} MB" -f $size)

# 4. Installer -------------------------------------------------------------------------------------
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { Write-Warning 'Inno Setup 6 not found, skipping installer (winget install -e --id JRSoftware.InnoSetup)'; exit 0 }
& $iscc /Q "/DAppVersion=$version" (Join-Path $root 'build-installer.iss')
if ($LASTEXITCODE) { throw 'ISCC failed' }
Write-Host 'ShoutSetup.exe built'
