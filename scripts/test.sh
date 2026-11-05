#!/usr/bin/env bash
set -Eeuo pipefail
python3 -I -B tests/test_setup.py -v
python3 -I -B -m unittest discover -s tests -p test_improvement_packet.py -v
