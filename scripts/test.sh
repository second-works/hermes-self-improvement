#!/usr/bin/env bash
set -Eeuo pipefail
python3 -B -m unittest discover -s tests -v
