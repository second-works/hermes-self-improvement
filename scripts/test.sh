#!/usr/bin/env bash
set -Eeuo pipefail
python3 -I -B tests/test_setup.py -v
# Offline admission and durable cloud-control contracts; never use real auth or Docker.
python3 -I -B -m unittest discover -s tests -p 'test_public_hermes.py' -v
python3 -I -B -m unittest discover -s tests -p 'test_mock_improvement.py' -v
