#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
task_python=${PYTHON:-.venv/bin/python}
task_output=${1:-artifacts/capacity-reproduction}
"$task_python" -m airspace_capacity --profile profiles/capacity-validation.json \
  --scenarios crossing corridor urban manned_intrusion sensor_outage wind_gust \
  --rates 120 360 720 --occupancy-limits 10 50 --seeds 7000 7001 7002 \
  --out "$task_output/baseline"
"$task_python" -m airspace_capacity --profile profiles/capacity-sensitivity.json \
  --scenarios crossing urban sensor_outage --rates 120 360 720 \
  --occupancy-limits 10 50 --seeds 7000 7001 7002 --out "$task_output/sensitivity"
"$task_python" -m airspace_capacity --profile profiles/capacity-density.json \
  --scenarios crossing --rates 3600 10800 --occupancy-limits 50 200 \
  --seeds 7000 7001 --out "$task_output/density"
"$task_python" -m airspace_capacity --profile profiles/capacity-layered-corridor.json \
  --rates 120 360 720 --occupancy-limits 10 --seeds 7000 7001 7002 \
  --out "$task_output/layered"
