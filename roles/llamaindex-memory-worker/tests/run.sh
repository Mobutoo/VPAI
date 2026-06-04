#!/bin/bash
set -uo pipefail; cd "$(dirname "$0")"; f=0
bash test_memctl.sh || f=1
bash test_memctl_remote.sh || f=1
python3 test_lock.py || f=1
[ "$f" = 0 ] && echo "ALL ROLE TESTS PASS" || { echo "ROLE TESTS FAILED"; exit 1; }
