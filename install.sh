#!/usr/bin/env bash
# Installateur VidAI — Linux / macOS.
#
# Vérifie les dépendances AVANT toute chose et ne fait RIEN sans te demander.
# Seule dépendance système obligatoire : Python >= 3.10. ffmpeg système est
# OPTIONNEL (VidAI en embarque un via imageio-ffmpeg). yt-dlp et faster-whisper
# sont tirés automatiquement par le paquet.
#
# Usage :
#   ./install.sh              # interactif
#   ./install.sh --yes        # accepte tout (non-interactif, ex. CI)
#   curl -fsSL https://raw.githubusercontent.com/daraook/vidai/main/install.sh | bash
#
set -euo pipefail

REPO="daraook/vidai"
PY_MIN_MINOR=10  # Python 3.10+

# ---------------------------------------------------------------- sortie / prompt
if [ -t 1 ]; then
  B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; C=$'\033[36m'; Z=$'\033[0m'
else
  B=''; G=''; Y=''; R=''; C=''; Z=''
fi
say()  { printf '%s\n' "${C}${*}${Z}"; }
ok()   { printf '%s\n' "  ${G}✓${Z} ${*}"; }
warn() { printf '%s\n' "  ${Y}!${Z} ${*}"; }
die()  { printf '%s\n' "${R}✗ ${*}${Z}" >&2; exit 1; }

ASSUME_YES=0
case "${1:-}" in --yes|-y) ASSUME_YES=1 ;; esac

# ask "question" -> 0 si oui. Lit /dev/tty (marche même via `curl | bash`).
ask() {
  [ "$ASSUME_YES" = "1" ] && return 0
  local reply
  if [ -r /dev/tty ]; then
    printf '%s [O/n] ' "$1" > /dev/tty
    read -r reply < /dev/tty || reply=""
  else
    warn "Pas de terminal interactif ; utilise --yes pour accepter automatiquement."
    return 1
  fi
  case "$reply" in ""|o|O|y|Y|oui|Oui|yes|Yes) return 0 ;; *) return 1 ;; esac
}

have() { command -v "$1" >/dev/null 2>&1; }

# ------------------------------------------------------------ package manager
PM=""
PM_INSTALL=""
if   have apt-get; then PM="apt";  PM_INSTALL="sudo apt-get install -y"
elif have dnf;     then PM="dnf";  PM_INSTALL="sudo dnf install -y"
elif have pacman;  then PM="pacman"; PM_INSTALL="sudo pacman -S --noconfirm"
elif have brew;    then PM="brew"; PM_INSTALL="brew install"
fi

pkg_install() {  # pkg_install <paquet> : propose puis installe via le PM détecté
  local pkg="$1"
  if [ -z "$PM" ]; then
    warn "Aucun gestionnaire de paquets connu (apt/dnf/pacman/brew) : installe « $pkg » manuellement."
    return 1
  fi
  if ask "Installer « $pkg » via $PM ?"; then
    say "→ $PM_INSTALL $pkg"
    $PM_INSTALL "$pkg"
  else
    return 1
  fi
}

# ------------------------------------------------------------------- Python 3.10+
PY=""
py_ok() { "$1" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, $PY_MIN_MINOR) else 1)" 2>/dev/null; }
for cand in python3 python; do
  if have "$cand" && py_ok "$cand"; then PY="$cand"; break; fi
done

say "${B}VidAI — installation${Z}"
say "1) Python >= 3.$PY_MIN_MINOR"
if [ -n "$PY" ]; then
  ok "$("$PY" --version 2>&1) ($(command -v "$PY"))"
else
  warn "Python >= 3.$PY_MIN_MINOR introuvable."
  case "$PM" in
    apt)    pkg_install python3 || true ;;
    dnf)    pkg_install python3 || true ;;
    pacman) pkg_install python  || true ;;
    brew)   pkg_install python  || true ;;
    *)      warn "Installe Python >= 3.$PY_MIN_MINOR depuis https://www.python.org/downloads/" ;;
  esac
  for cand in python3 python; do
    if have "$cand" && py_ok "$cand"; then PY="$cand"; break; fi
  done
  [ -n "$PY" ] || die "Python >= 3.$PY_MIN_MINOR toujours absent. Installe-le puis relance."
  ok "$("$PY" --version 2>&1)"
fi

# --------------------------------------------------------------------- pipx
say "2) pipx (installe VidAI dans un environnement isolé)"
if have pipx; then
  ok "pipx présent"
else
  warn "pipx absent."
  installed=0
  case "$PM" in
    apt|dnf|pacman|brew) if pkg_install pipx; then installed=1; fi ;;
  esac
  if [ "$installed" = "0" ] && ! have pipx; then
    if ask "Installer pipx via « $PY -m pip install --user pipx » ?"; then
      "$PY" -m pip install --user pipx
      "$PY" -m pipx ensurepath || true
    fi
  fi
  have pipx || warn "pipx indisponible : on tentera « pip install --user » en dernier recours."
fi

# ------------------------------------------------------------------- ffmpeg (OPTIONNEL)
say "3) ffmpeg système (OPTIONNEL — VidAI en embarque un via imageio-ffmpeg)"
if have ffmpeg; then
  ok "ffmpeg système présent (utilisé en fallback)"
else
  warn "Pas de ffmpeg système : ce n'est PAS bloquant, VidAI utilise le binaire bundlé."
  if ask "Installer quand même ffmpeg système (fallback / performances) ?"; then
    pkg_install ffmpeg || true
  fi
fi

# ------------------------------------------------------------------- install VidAI
say "4) Installation de VidAI"
GIT_SRC="git+https://github.com/${REPO}.git"

# Cherche le wheel de la dernière release GitHub (install rapide, sans build).
wheel_url() {
  have curl || return 1
  curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null \
    | grep -oE '"browser_download_url": *"[^"]+\.whl"' | head -1 | cut -d'"' -f4
}

install_target=""
WHEEL="$(wheel_url || true)"
if [ -n "${WHEEL:-}" ]; then
  ok "Release trouvée : $(basename "$WHEEL")"
  install_target="$WHEEL"
else
  warn "Aucune release/wheel publiée : installation depuis les sources ($GIT_SRC)."
  have git || die "git requis pour l'install depuis les sources. Installe git ou publie une release."
  install_target="$GIT_SRC"
fi

if have pipx; then
  say "→ pipx install --force $install_target"
  pipx install --force "$install_target"
else
  say "→ $PY -m pip install --user --upgrade $install_target"
  "$PY" -m pip install --user --upgrade "$install_target"
fi

# ------------------------------------------------------------------- vérification
say "5) Vérification"
if have vidai; then
  vidai --check || warn "vidai --check a signalé un souci (voir ci-dessus)."
  ok "${B}Installé.${Z} Lance : ${B}vidai \"<url>\" -o ./out${Z}"
else
  warn "La commande « vidai » n'est pas encore dans le PATH."
  warn "Ouvre un nouveau terminal, ou exécute : $PY -m pipx ensurepath  (puis relance ton shell)."
fi
