#!/bin/bash
# SessionStart hook for Claude Code on the web.
#
# Installs the project's dependencies so the test suite and the tool itself can
# run in a fresh, ephemeral container. Idempotent and non-interactive.
set -euo pipefail

# Only run in the remote (web) environment; local setups manage their own deps.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Python dev dependencies (pytest, pytest-cov) — required to run the test suite.
PIP_ROOT_USER_ACTION=ignore python3 -m pip install --quiet -e ".[dev]"

# exiftool — runtime dependency of the tool (not a pip package). Best-effort:
# the test suite mocks subprocess and passes without it, but real runs need it.
# Tolerates third-party PPA failures in `apt-get update` (main archive is enough).
if ! command -v exiftool >/dev/null 2>&1; then
  apt-get update -qq || true
  apt-get install -y -qq libimage-exiftool-perl \
    || echo "session-start: could not install exiftool (apt unavailable?)" >&2
fi
