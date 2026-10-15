#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

stage_count=0

skip_stage() {
  local stage="$1"
  local reason="$2"
  printf '[verify] stage=%s skipped reason=%s\n' "${stage}" "${reason}"
}

run_stage() {
  local stage="$1"
  shift
  stage_count=$((stage_count + 1))
  printf '[verify] stage=%s started\n' "${stage}"
  if "$@"; then
    printf '[verify] stage=%s passed\n' "${stage}"
  else
    local status=$?
    printf '[verify] stage=%s failed exit=%s\n' "${stage}" "${status}" >&2
    exit "${status}"
  fi
}

require_command() {
  local command_name="$1"
  local stage="$2"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf '[verify] stage=%s failed reason=required command %s is not installed\n' "${stage}" "${command_name}" >&2
    exit 127
  fi
}

npm_script_status() {
  node -e '
    const fs = require("fs");
    try {
      const packageJson = JSON.parse(fs.readFileSync("package.json", "utf8"));
      const scriptName = process.argv[1];
      process.exit(typeof packageJson.scripts?.[scriptName] === "string" ? 0 : 1);
    } catch (error) {
      console.error(error.message);
      process.exit(2);
    }
  ' "$1" >/dev/null 2>&1
}

run_optional_npm_stage() {
  local stage="$1"
  local script_name="$2"
  if npm_script_status "${script_name}"; then
    run_stage "${stage}" npm run "${script_name}"
  else
    local status=$?
    if [[ "${status}" -eq 1 ]]; then
      skip_stage "${stage}" "package.json has no scripts.${script_name}"
    else
      printf '[verify] stage=%s failed reason=package.json could not be inspected exit=%s\n' "${stage}" "${status}" >&2
      exit "${status}"
    fi
  fi
}

has_python_tests() {
  [[ -d tests ]] && [[ -n "$(find tests -type f \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit)" ]]
}

has_ruff_config() {
  [[ -f ruff.toml || -f .ruff.toml ]] || {
    [[ -f pyproject.toml ]] && grep -qE '^\[tool\.ruff([.]|\])' pyproject.toml
  }
}

has_mypy_config() {
  [[ -f mypy.ini || -f .mypy.ini ]] || {
    [[ -f pyproject.toml ]] && grep -qE '^\[tool\.mypy\]' pyproject.toml
  } || {
    [[ -f setup.cfg ]] && grep -qE '^\[mypy\]' setup.cfg
  }
}

has_python_build_config() {
  [[ -f pyproject.toml ]] && grep -qE '^\[build-system\]' pyproject.toml
}

run_node_stages() {
  require_command node node
  run_optional_npm_stage lint lint
  run_optional_npm_stage 'type check' typecheck
  run_optional_npm_stage test test
  run_optional_npm_stage build build
}

run_python_stages() {
  if has_ruff_config; then
    run_stage lint ruff check .
  else
    skip_stage lint 'no Ruff configuration found'
  fi

  if has_mypy_config; then
    run_stage 'type check' mypy .
  else
    skip_stage 'type check' 'no mypy configuration found'
  fi

  if has_python_tests; then
    run_stage test pytest -q
  else
    skip_stage test 'no Python test files found'
  fi

  if has_python_build_config; then
    run_stage build python -m build
  else
    skip_stage build 'no PEP 517 build configuration found'
  fi
}

run_generic_stages() {
  local stage
  local script
  for stage in lint typecheck test build; do
    script="${ROOT_DIR}/scripts/${stage}.sh"
    if [[ -x "${script}" ]]; then
      run_stage "${stage}" "${script}"
    else
      skip_stage "${stage}" "${script} is not executable"
    fi
  done
}

has_python_project() {
  [[ -f pyproject.toml || -f setup.py || -f uv.lock || -f poetry.lock ]] ||
    compgen -G 'requirements*.txt' >/dev/null
}

stack="${VERIFY_STACK:-auto}"
if [[ "${stack}" == auto ]]; then
  if [[ -f package.json ]]; then
    stack=node
  elif has_python_project; then
    stack=python
  else
    stack=generic
  fi
fi

case "${stack}" in
  node)
    [[ -f package.json ]] || { printf '[verify] stack=node requires package.json\n' >&2; exit 2; }
    run_node_stages
    ;;
  python)
    has_python_project || {
      printf '[verify] stack=python requires a Python project marker (pyproject.toml, setup.py, requirements*.txt, uv.lock, poetry.lock)\n' >&2
      exit 2
    }
    run_python_stages
    ;;
  generic)
    run_generic_stages
    ;;
  *)
    printf '[verify] unsupported VERIFY_STACK=%s\n' "${stack}" >&2
    exit 2
    ;;
esac

if ((stage_count == 0)); then
  printf '[verify] failed reason=no applicable verification stages configured\n' >&2
  exit 2
fi

printf '[verify] completed stack=%s applicable_stages=%s\n' "${stack}" "${stage_count}"
