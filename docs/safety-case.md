# Conditional safety case

This document specifies obligations for a future implementation. None of the obligations is discharged by the presence of these equations or by ASTM interface qualification.

## Claim and required assumptions

For an equipped aircraft i, physical intersection with every relevant traffic object j is prevented while all of the following hold:

| Assumption | Required evidence or response |
|---|---|
| A1 Coverage | Every object that can enter the protected region is detected with a bounded delay and physically enclosed. RID-only coverage must be demonstrated; add independent sensors or limit the region. |
| A2 Truth enclosure | True position, velocity and motion stay within the safety state/dynamic sets. Accuracy flags or authenticated self-reports alone do not establish this. |
| A3 Timing | Source age, receiver clock error, compute, transport, sample/hold and actuation delay stay within proved bounds. |
| A4 Control authority | Actual closed-loop acceleration/tracking and disturbances obey the certified bounds, including battery, wind, tilt and payload effects. |
| A5 Initial viability | The aircraft starts in the robust safe set and has a feasible backup. Positive distance alone is insufficient. |
| A6 Recursive feasibility | All simultaneous hard constraints can be met or a validated backup remains valid; new object/uncertainty updates preserve this condition. |
| A7 Correct implementation | Numeric error, solver status, memory, frame transforms and watchdog behavior match the verified model. |

No assumption requires another aircraft to run this negotiation protocol. A bounded legacy aircraft need not acknowledge or yield. However, an intruder with unrestricted adversarial acceleration or persistent superior pursuit capability can make avoidance impossible. No controller guarantees safety from an arbitrary initial collision course in arbitrarily dense traffic.

## Protected volumes

The initial simulation uses a conservative spherical center-distance boundary. Define

\[
R_{ij}=\max(r_i^{body}+r_j^{body}+m_{operational},R_{floor})
+\epsilon_{p,i}+\epsilon_{p,j}+e_{track,i}+e_{track,j}+m_{sample}.
\]

Rotor and downwash geometry may require a larger or anisotropic envelope. The example `R_floor = 10 m` includes the minimum desired center separation before uncertainty inflation; it is not 10 m added to an already identical operational boundary. A future horizontal/vertical well-clear cylinder must be handled as a union of safe regions, not by simply replacing it with an ellipsoid: an ellipsoid excludes a smaller volume than a cylinder with the same axes. Any smooth outer approximation must be shown to contain the full protected volume.

Navigation, clock and prediction uncertainty can be represented through the state enclosure or radius inflation. Do not count the same error twice when mapping the model to code. A declared missing body radius uses a validated maximum for the allowed operating domain; otherwise the bound is unknown. Geofence/terrain constraints also need navigation, transform and tracking margins.

## Derivation of the barrier condition

For illustrative constant R and double-integrator relative dynamics,

\[
\dot r=w,\qquad \dot w=u_i-u_j+d,
\quad h=r^Tr-R^2,
\]

\[
\dot h=2r^Tw,\quad
\ddot h=2w^Tw+2r^T(u_i-u_j+d).
\]

Choose positive gains k1 and k2, define `psi1 = h_dot + k1 h`, and require

\[
\dot\psi_1+k_2\psi_1
=\ddot h+(k_1+k_2)\dot h+k_1k_2h\ge0.
\]

Under the requisite regularity, feasibility and initial conditions `h >= 0` and `psi1 >= 0`, comparison arguments preserve both inequalities and hence protected separation. This higher-order construction handles acceleration control; merely constraining `h_dot + k h` cannot choose u in these dynamics. [Higher-order CBF basis](https://arxiv.org/abs/1903.04706).

Evaluate the condition robustly over every possible true state and other-aircraft input in the validated enclosure. For fixed r and a spherical acceleration set `||u_j|| <= a_j`,

\[
\inf_{u_j}(-2r^Tu_j)=-2a_j\|r\|.
\]

The relative disturbance bound contributes another worst-case support term. With uncertain r and w, this simple fixed-state expression is insufficient. A verified interval bound or conservative analytic support bound must cover their full set and the ownship input dependence. An affine robust lower bound `A_ij u_i >= b_ij` can feed a QP; taking a few corner samples of a nonlinear expression is not a proof. The base [CBF/QP framework](https://arxiv.org/abs/1609.06408) motivates this filter, while the enclosure and aircraft integration remain project proof obligations.

## Sampled control and changing enclosures

At each safety tick, certify the condition over the complete command-hold interval plus bounded execution delay, not only at the sampling instant. Derive a Lipschitz/interval margin over the reachable slab and include solver roundoff in the lower bound. The 50 Hz example is a proposed compute rate, not evidence that a continuous-time proof carries over.

If R changes smoothly with time, use

\[
\dot h=2r^Tw-2R\dot R,\quad
\ddot h=2w^Tw+2r^T\dot w-2\dot R^2-2R\ddot R.
\]

Alternatively, use a conservative constant radius/enclosure valid throughout each verified interval. At a change of observation, association or profile, establish membership in the new safe set before proceeding. A sudden uncertainty increase can reveal that the aircraft was never certifiably separated; an updated barrier cannot retrospectively guarantee safety. Retain the old threat enclosure until a sound update permits tightening.

Map proposed accelerations to the actual autopilot through a validated inner-loop tracking enclosure. Include thrust limits, speed/jerk constraints and attainable lateral maneuvers. A positive QP result for an unattainable acceleration is not safe. Safety-command arbitration is local and higher priority than mission planning; pilot/autopilot modes bypassing it fall outside this claim and must be explicitly recorded.

## Backup and multi-aircraft feasibility

Define a backup set B with a controller that preserves collision, terrain and other mandatory constraints for the bounded operating horizon or a proven invariant region. Every nominal executed prefix must keep all enclosed states within the predecessor of B, covering communication and solver faults. Reverify transitions between backup and nominal controllers.

The robust input assumptions must cover *other aircraft's own safety overrides*, not only their nominal plan. Independent pairwise constraints do not guarantee a common feasible control when several obstacles surround an aircraft. Solve the full intersection, establish recursive feasibility, and reject admissions before it disappears. Capacity controls reserve escape/staging volumes across USS boundaries; legacy entries reduce available capacity dynamically.

A backup that is valid only after every other aircraft also brakes is unsuitable for the initial profile. Hovering in a corridor may be struck by a legacy drone, climbing may hit another aircraft or terrain restriction, and landing may expose people. Each backup needs an actual reachable-set certificate from the current enclosure. If no safe action exists, record infeasibility and use an assessed emergency response without claiming collision freedom.

## Detection and timing budget

Detection must occur while avoidance remains feasible. As a scalar *screening approximation*, suppose closure speed is at most c, no-action/reaction delay is tau, and an escape maneuver guarantees that closure decreases by at least `a_rel > 0` throughout the closure-arrest phase. Then

\[
d_{detect}\ge R+c\tau+\frac{c^2}{2a_{rel}}+m_{coverage}.
\]

This is not a general 3D theorem. Its constant-closure delay assumption must be replaced by `c tau + 0.5 a_close tau^2` and the higher closure speed at the end of that delay when acceleration during delay is possible. Subsequent motion still requires a viable escape; simply stopping ownship does not prevent a moving intruder from hitting it.

For illustration only, `R = 20 m`, `c = 20 m/s`, `tau = 0.5 s`, `a_rel = 4 m/s²`, and `m_coverage = 10 m` produce **90 m** using the simplified assumptions. A one-second observation-age increase alone consumes another 20 m at constant closure. If full legacy acceleration bounds make `a_rel <= 0`, this screening formula supplies no safety guarantee: use validated lateral/vertical reachability or prohibit the encounter geometry. The chosen example does not establish a radio receiver range or flight permission.

The actual admission criterion is that sensing coverage and current enclosures permit a verified escape before the protected tube can intersect. Include RF occlusion, scanning gaps, packet collisions, receiver processing, telemetry transport and actual command response. The example 0.5 s fresh-track threshold is a policy trigger, not a promised RID update rate. A stale track grows until independent evidence or an operating-domain exclusion resolves it.

## Well-clear and assurance separation

DAIDALUS supplies deterministic well-clear detection/alerting and kinematic guidance for its configured models. Use a profile matched to the operation and preserve provenance of configuration and implementation. Formal results for a library's core logic do not prove sensor coverage, a custom threshold profile, end-to-end timing or actuator response. [NASA formal-methods description](https://shemesh.larc.nasa.gov/fm/DAIDALUS/).

The initial spherical shield is a proposed UAS safety boundary. Additional applicable well-clear requirements can impose larger or different exclusion volumes. A deployment must verify all applicable constraints, rather than equating a small center-distance bound with DO-365 well-clear compliance.

## Failure of an assumption

Detect assumption failures where possible through sensor-health reporting, independent physical measurements, deadline watchdogs, actuator tracking monitors and residual checks. A runtime monitor may detect a violation too late to avoid collision; monitoring itself is not proof of prevention. On loss of a required bound, close admissions, enlarge uncertainty, invoke a currently valid backup if one exists, and retain evidence of when the guarantee ceased to apply.
