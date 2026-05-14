#!/usr/bin/env bash
# Launch sdm_manager_gui.py with a Python that has a working Tcl/Tk on macOS.
# /usr/bin/python3 (Xcode CLT) often crashes with:
#   macOS 26 (...) or later required, have instead 16 (...) !
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
GUI="$DIR/sdm_manager_gui.py"

try_tk() {
  local py="$1"
  [[ -n "$py" && -x "$py" ]] || return 1
  # Subshell so SIGABRT from a bad Tk build does not kill this script outright.
  if ("$py" -c "import tkinter as t; r=t.Tk(); r.withdraw(); r.destroy()" >/dev/null 2>&1); then
    return 0
  fi
  return 1
}

if [[ "$(uname -s)" == "Darwin" ]]; then
  PYS=()
  command -v python3.14 &>/dev/null && PYS+=("$(command -v python3.14)")
  command -v python3.13 &>/dev/null && PYS+=("$(command -v python3.13)")
  if command -v brew &>/dev/null; then
    for v in 3.14 3.13; do
      bp="$(brew --prefix "python@${v}" 2>/dev/null || true)"
      [[ -n "$bp" && -x "$bp/bin/python${v}" ]] && PYS+=("$bp/bin/python${v}")
    done
  fi
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    [[ -x "$p" ]] && PYS+=("$p")
  done

  for py in "${PYS[@]}"; do
    if try_tk "$py"; then
      exec "$py" "$GUI" "$@"
    fi
  done

  echo "No Python with a working Tk (tkinter) was found." >&2
  echo "" >&2
  echo "Apple's /usr/bin/python3 often ships a Tk that aborts on recent macOS." >&2
  echo "Install Homebrew Python + Tk, then re-run this script:" >&2
  echo "  brew install python@3.14 python-tk@3.14" >&2
  echo "  ./run_sdm_gui_macos.sh" >&2
  echo "" >&2
  echo "Or install Python from https://www.python.org/downloads/macos/ (includes Tcl/Tk 8.6)." >&2
  exit 1
fi

exec python3 "$GUI" "$@"
