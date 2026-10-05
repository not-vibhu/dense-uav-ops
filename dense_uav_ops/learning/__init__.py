"""Optional learned ranking of planner candidates (requires the `learning` extra: torch).

Learned policies only choose among candidates the planner has already found
admissible. They cannot change separation requirements, assumed traffic
accelerations, vehicle envelopes or the fallback used when nothing is
admissible. A learned policy therefore changes efficiency and which admissible
maneuver is flown; it cannot create admissible maneuvers where none exist.

Checkpoints are JSON arrays of finite tensors (no pickle). Each records the
environment seeds used for training, which are refused at evaluation time.
"""

OBSERVATION_VERSION = 'own17-neighbors8x11-v1'
