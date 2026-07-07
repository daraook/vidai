# Installateur VidAI — Windows (PowerShell).
#
# Vérifie les dépendances AVANT toute chose et ne fait RIEN sans te demander.
# Seule dépendance système obligatoire : Python >= 3.10. ffmpeg système est
# OPTIONNEL (VidAI en embarque un via imageio-ffmpeg). yt-dlp et faster-whisper
# sont tirés automatiquement par le paquet.
#
# Usage :
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Yes   # non-interactif
#
param([switch]$Yes)

$ErrorActionPreference = "Stop"
$Repo = "daraook/vidai"
$PyMinMinor = 10

function Say  ($m) { Write-Host $m -ForegroundColor Cyan }
function Ok   ($m) { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "[x] $m" -ForegroundColor Red; exit 1 }

function Ask ($q) {
  if ($Yes) { return $true }
  $r = Read-Host "$q [O/n]"
  return ($r -eq "" -or $r -match '^(o|y|oui|yes)$')
}

function Have ($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function WingetInstall ($id) {
  if (-not (Have winget)) { Warn "winget absent : installe « $id » manuellement."; return $false }
  if (Ask "Installer « $id » via winget ?") {
    Say "-> winget install --silent --accept-package-agreements --accept-source-agreements $id"
    winget install --silent --accept-package-agreements --accept-source-agreements $id
    return $true
  }
  return $false
}

Say "VidAI - installation"

# 1) Python >= 3.10 -------------------------------------------------------------
Say "1) Python >= 3.$PyMinMinor"
$Py = $null
foreach ($cand in @("python", "python3", "py")) {
  if (Have $cand) {
    $okver = & $cand -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, $PyMinMinor) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $Py = $cand; break }
  }
}
if ($Py) {
  Ok ((& $Py --version) 2>&1)
} else {
  Warn "Python >= 3.$PyMinMinor introuvable."
  WingetInstall "Python.Python.3.12" | Out-Null
  foreach ($cand in @("python", "python3", "py")) {
    if (Have $cand) {
      & $cand -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, $PyMinMinor) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { $Py = $cand; break }
    }
  }
  if (-not $Py) { Die "Python >= 3.$PyMinMinor toujours absent. Installe-le puis relance (ferme/rouvre le terminal)." }
  Ok ((& $Py --version) 2>&1)
}

# 2) pipx -----------------------------------------------------------------------
Say "2) pipx (installe VidAI dans un environnement isolé)"
if (Have pipx) {
  Ok "pipx present"
} else {
  Warn "pipx absent."
  if (Ask "Installer pipx via « $Py -m pip install --user pipx » ?") {
    & $Py -m pip install --user pipx
    & $Py -m pipx ensurepath
    Warn "Ferme puis rouvre ce terminal si « pipx » n'est pas encore reconnu."
  }
}

# 3) ffmpeg systeme (OPTIONNEL) -------------------------------------------------
Say "3) ffmpeg systeme (OPTIONNEL - VidAI en embarque un via imageio-ffmpeg)"
if (Have ffmpeg) {
  Ok "ffmpeg systeme present (fallback)"
} else {
  Warn "Pas de ffmpeg systeme : NON bloquant, VidAI utilise le binaire bundle."
  if (Ask "Installer quand meme ffmpeg systeme (fallback / performances) ?") {
    WingetInstall "Gyan.FFmpeg" | Out-Null
  }
}

# 4) Installation de VidAI ------------------------------------------------------
Say "4) Installation de VidAI"
$GitSrc = "git+https://github.com/$Repo.git"
$Target = $null
try {
  $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "vidai-install" }
  $wheel = $rel.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
  if ($wheel) { $Target = $wheel.browser_download_url; Ok "Release trouvee : $($wheel.name)" }
} catch { }
if (-not $Target) {
  Warn "Aucune release/wheel publiee : installation depuis les sources ($GitSrc)."
  if (-not (Have git)) { Die "git requis pour l'install depuis les sources. Installe git ou publie une release." }
  $Target = $GitSrc
}

if (Have pipx) {
  Say "-> pipx install --force $Target"
  pipx install --force $Target
} else {
  Say "-> $Py -m pip install --user --upgrade $Target"
  & $Py -m pip install --user --upgrade $Target
}

# 5) Verification ---------------------------------------------------------------
Say "5) Verification"
if (Have vidai) {
  vidai --check
  Ok "Installe. Lance : vidai `"<url>`" -o .\out"
} else {
  Warn "La commande « vidai » n'est pas encore dans le PATH."
  Warn "Ouvre un nouveau terminal, ou execute : $Py -m pipx ensurepath  (puis relance ton shell)."
}
