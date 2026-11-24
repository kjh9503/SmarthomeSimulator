#!/bin/sh
# Rebuild the three TEST profiles and draw their habits (see tools/make_test_profiles.py).
set -e
cd "$(dirname "$0")/.."
python3 tools/make_test_profiles.py
for p in test_office test_remote test_retiree; do
  for s in phone heating ventilation cooling window hood shower laundry drying home_base; do
    python3 pipeline/sample_${s}_person.py profiles/$p.json > /dev/null
  done
  python3 pipeline/check_profile.py profiles/$p.json | tail -1
done
