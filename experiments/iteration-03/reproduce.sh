#!/bin/sh
set -eu
# Run from the repository root. Full catalog: 648 paired runs; total development suite: 948 runs.
PYTHON=${SWARM_PYTHON:-.venv/bin/python}
for seed in 42 43; do
  if [ "$seed" = 42 ]; then directory=models; else directory=models/seed-43; fi
  "$PYTHON" -m swarm_sim train-imitation --episodes 8 --epochs 12 --duration 24 --training-seed "$seed" --out "$directory/imitation.json"
  "$PYTHON" -m swarm_sim train-mappo --episodes 8 --epochs 3 --duration 24 --training-seed "$seed" --initial "$directory/imitation.json" --out "$directory/mappo.json"
done
for mode in off checked; do
  if [ "$mode" = off ]; then routes=off; else routes=visibility; fi
  "$PYTHON" -m swarm_sim compare --scenarios all --counts 10 50 --fractions .5 \
    --controllers predictive imitation mappo --discovery-seeds 5000 --holdout-seeds 6000 \
    --duration 36 --admission "$mode" --admission-limit 40 --routes "$routes" \
    --imitation-checkpoint models/imitation.json --mappo-checkpoint models/mappo.json \
    --workers 4 --out "artifacts/iteration03-$mode"
done
"$PYTHON" -m swarm_sim compare --scenarios crossing urban overload outage_turn --counts 10 50 --fractions .5 \
  --controllers predictive imitation mappo --discovery-seeds 5000 --holdout-seeds 6000 --duration 36 \
  --admission capacity --admission-limit 40 --routes visibility --imitation-checkpoint models/imitation.json \
  --mappo-checkpoint models/mappo.json --workers 4 --out artifacts/iteration03-capacity
"$PYTHON" -m swarm_sim compare --scenarios crossing urban overload outage_turn --counts 10 50 --fractions .5 \
  --controllers predictive imitation mappo --discovery-seeds 5000 --holdout-seeds 6000 --duration 36 \
  --admission off --admission-limit 40 --routes visibility --imitation-checkpoint models/imitation.json \
  --mappo-checkpoint models/mappo.json --workers 4 --out artifacts/iteration03-routes
"$PYTHON" -m swarm_sim compare --scenarios all --counts 10 --fractions .5 \
  --controllers imitation mappo --discovery-seeds 5000 --holdout-seeds 6000 --duration 36 \
  --admission checked --admission-limit 40 --routes visibility --imitation-checkpoint models/seed-43/imitation.json \
  --mappo-checkpoint models/seed-43/mappo.json --workers 4 --out artifacts/iteration03-seed43
for mode in off checked; do
  "$PYTHON" -m swarm_sim compare --scenarios crossing overload --counts 100 200 --fractions .5 \
    --controllers predictive imitation mappo --discovery-seeds 5000 --holdout-seeds 6000 --duration 36 \
    --admission "$mode" --admission-limit 120 --routes visibility --imitation-checkpoint models/imitation.json \
    --mappo-checkpoint models/mappo.json --workers 4 --out "artifacts/iteration03-scale-$mode"
done

"$PYTHON" -m swarm_sim compare --scenarios crossing urban overload outage_turn --counts 10 50 --fractions 1 \
  --controllers predictive imitation mappo --discovery-seeds 5000 --holdout-seeds 6000 --duration 36 \
  --admission checked --admission-limit 40 --routes visibility --imitation-checkpoint models/imitation.json \
  --mappo-checkpoint models/mappo.json --workers 4 --out artifacts/iteration03-full-cooperation

"$PYTHON" - <<'PYTHON'
from swarm_sim.config import Config
from swarm_sim.engine import simulate
from swarm_sim.cli import write_json,source_hash
runs=[simulate(Config(controller='predictive',drones=10,cooperative_fraction=1.,fixed_wing_fraction=f,duration=36,seed=6000,admission='checked',routes='visibility',require_invariant_backup=True)) for f in [0.,.4,1.]]
write_json('artifacts/iteration03-strict-terminal.json',{'source_sha256':source_hash(),'runs':runs})
PYTHON
"$PYTHON" -m pip freeze > artifacts/iteration03-environment.txt
"$PYTHON" < experiments/iteration-03/validate_and_publish.py
