# Development checkpoints

These JSON files are research checkpoints for version 0.3, not flight policies. They use the fixed attention/GRU schema implemented in `swarm_sim/learning.py`; no pickle deserialization is used.

- `imitation.json` and `mappo.json`: optimizer seed 42, selected as the primary development pair before the final comparisons.
- `seed-43/`: second independent optimizer seed. It is checked against all 27 scenarios at 10 aircraft with mixed cooperation, rather than used to choose a favorable checkpoint.
- `*.training.json`: training metrics, rollout configurations and a checkpoint digest. Training rollouts are not evaluation evidence.

Imitation uses eight 24-second episodes, five cooperative aircraft among ten requested aircraft, 40% fixed-wing, static routing and checked admission. Scenario order is head-on, crossing, overtaking and urban, repeated once, with environment seeds 4000–4007. Twelve training epochs use admissible teacher decisions only. MAPPO uses the same eight environment configurations, three PPO epochs per on-policy episode, and begins from the corresponding imitation checkpoint. The small budget establishes a working training pipeline; it is not evidence of convergence.

Loading requires the recorded simulator source revision. Retrain deliberately after source changes. Campaigns pin file digests and reject training/evaluation seed overlap. Final evaluation seeds are 5000 and 6000, with only 6000 used for holdout reporting. Numeric tensor arrays and metadata are inspectable in each file. SHA-256 pins provide integrity relative to a trusted manifest; they do not establish publisher authenticity without an external signed anchor.
