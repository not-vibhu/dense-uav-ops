# Sources and integration revisions

Reviewed on 4 October 2026. Sources below establish standards scope, existing interfaces and algorithmic foundations. The combined architecture, protocol, fairness objective, example timings, proof obligations and acceptance plan are project proposals. Public ASTM scope pages are not substitutes for the licensed normative documents.

## Primary sources

| Reference | What it supports |
|---|---|
| [ASTM F3411-22a](https://store.astm.org/f3411-22a.html) | Broadcast and Network Remote ID scope and interoperability role. |
| [ASTM F3548-21](https://store.astm.org/f3548-21.html) | Strategic coordination scope; tactical conflicts and fairness requirements are excluded from this edition's guarantees. |
| [InterUSS DSS](https://github.com/interuss/dss) and [concepts](https://github.com/interuss/dss/blob/master/concepts.md) | Discovery/synchronization, RID provider discovery, telemetry queries and USS interoperability. |
| [InterUSS RID version guidance](https://github.com/interuss/dss/blob/master/interfaces/rid/README.md) | Version-mixing pitfalls and endpoint semantics. |
| [InterUSS monitoring](https://github.com/interuss/monitoring) | USS qualification and interoperability testing capabilities. |
| [OpenUTM Flight Blender](https://github.com/openutm/flight-blender) and [plugins](https://github.com/openutm/flight-blender/blob/master/PLUGINS.md) | Existing USS backend, traffic/RID integration and plugin boundaries. |
| [OpenUTM verification](https://github.com/openutm/verification) | Upstream scenario/verification tooling; tactical evidence must be added separately. |
| [OpenDroneID core C](https://github.com/opendroneid/opendroneid-core-c) | Broadcast message encoding/decoding and Bluetooth/Wi-Fi integration. |
| [Bernstein, Givan, Immerman and Zilberstein](https://cics.umass.edu/~immerman/pub/bgiz.pdf), 2002 | Decentralized partially observable control model and computational complexity. |
| [ORCA authors' project](https://gamma-web.iacs.umd.edu/ORCA/) | Reciprocal shared-responsibility avoidance premise and algorithm context. |
| [Ames, Xu, Grizzle and Tabuada](https://arxiv.org/abs/1609.06408), published 2017 | CBF constraints and optimization for safety/performance control. |
| [Xiao and Belta](https://arxiv.org/abs/1903.04706), 2019 | Higher-order barriers for constraints with high relative degree. |
| [NASA DAIDALUS formal methods](https://shemesh.larc.nasa.gov/fm/DAIDALUS/) and [current source](https://github.com/nasa/daidalus) | Well-clear algorithms, guidance and formal-methods foundations. |
| [DAIDALUS manual](https://nasa.github.io/daidalus/) | Input assumptions, ownship guidance, uncertainty interfaces and configuration semantics. |
| [ICAROUS documentation](https://nasa.github.io/icarous/) and [modules](https://github.com/nasa/icarous/tree/4a3bcf443e516c713c775bd6d32b8184d57c4ea2/Modules) | Onboard module boundaries, cognition, traffic monitoring, guidance and merge scheduling. |
| [RFC 9575](https://www.rfc-editor.org/rfc/rfc9575.html) | DRIP broadcast RID authentication formats; optional for equipped aircraft. |
| [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html) | Merkle inclusion/consistency and signed transparency checkpoints; primitives adapted here for tactical evidence. |

No proprietary normative standard text is copied into this repository. No newly invented tactical interface is attributed to ASTM or InterUSS.

## Locally inspected integration pins

These are the workspace revisions consulted, not assertions that they are the latest upstream release or have passed tests in this environment:

| Project | Local HEAD |
|---|---|
| InterUSS DSS | `49bda8e1b457af90d840330bfb5ac8396f4def27` |
| InterUSS monitoring | `119dda535964fa10cab600b45ff68a1fe3de5d54` |
| OpenUTM Flight Blender | `be709a78b3feac019c2cb7dcb557e0e7642b17f4` |
| OpenUTM verification | `800d1f5d15dbb6cea0f93df5e407122f1fe84617` |
| NASA DAIDALUS | `1c7b58e5525d5cca91cbbf4a8b7337a488243769` |
| NASA ICAROUS study | `4a3bcf443e516c713c775bd6d32b8184d57c4ea2` |

The v0.4 DAIDALUS C++ library and original bridge were built and tested locally. ICAROUS source was studied, but its complete runtime was not built. See the [implementation guide](nasa-and-distributed-development.md) and `integrations/daidalus/pins.json`; NASA software is fetched separately under its upstream license.

Concrete Flight Blender integration references:

- [Telemetry router](https://github.com/openutm/flight-blender/blob/be709a78b3feac019c2cb7dcb557e0e7642b17f4/src/flight_blender/api/routers/flight_feed_api.py): telemetry, signed telemetry and air-traffic ingress.
- [RID router](https://github.com/openutm/flight-blender/blob/be709a78b3feac019c2cb7dcb557e0e7642b17f4/src/flight_blender/api/routers/rid_api.py): RID discovery helpers and USS provider interfaces.
- [RID task processing](https://github.com/openutm/flight-blender/blob/be709a78b3feac019c2cb7dcb557e0e7642b17f4/src/flight_blender/tasks/rid_task.py): telemetry processing and observation normalization.
- [Redis stream helper](https://github.com/openutm/flight-blender/blob/be709a78b3feac019c2cb7dcb557e0e7642b17f4/src/flight_blender/clients/redis_client.py): existing stream operations, distinct from a proven real-time safety bus.
- [Plugin contracts](https://github.com/openutm/flight-blender/blob/be709a78b3feac019c2cb7dcb557e0e7642b17f4/PLUGINS.md): strategic declaration deconfliction, traffic fusion and volume generation.

Qualify exact deployed revisions, normative editions, interface schemas and security configuration before integrating. Treat upstream feature/compliance claims as capabilities to verify rather than certification evidence for this architecture.
