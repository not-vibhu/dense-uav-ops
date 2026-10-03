"""Capacity is a tested operating envelope, not a product of quality scores."""
from dataclasses import asdict
import hashlib
import json
import math


SAFETY_COUNTERS = ('collision_pairs', 'protected_volume_breach_pairs',
                   'obstacle_collision_pairs', 'body_volume_exit_aircraft',
                   'kinematic_violation_aircraft_steps', 'no_admissible_aircraft_steps')
SAFETY_COUNTERS += ('control_failure_aircraft_steps', 'endurance_exceeded_aircraft_steps')
SAFETY_COUNTERS += ('command_deadline_misses', 'unobserved_manned_aircraft_steps', 'occupancy_overflow_steps')


def identity(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True, allow_nan=False).encode()).hexdigest()[:16]


def upper_failure_probability(failures, trials, alpha):
    """One-sided exact Clopper–Pearson bound; independent runs are the unit.

    Solve P_p[Binomial(n,p) <= failures] = alpha. No SciPy dependency.
    """
    if trials < 1 or not 0 <= failures <= trials or not 0 < alpha < 1:
        raise ValueError('Invalid binomial bound inputs')
    if failures == trials:
        return 1.
    if failures == 0:
        return -math.expm1(math.log(alpha) / trials)
    low, high = 0., 1.
    for _ in range(70):
        p = (low+high)/2
        terms = [math.lgamma(trials+1)-math.lgamma(k+1)-math.lgamma(trials-k+1) +
                 k*math.log(p)+(trials-k)*math.log1p(-p) for k in range(failures+1)]
        peak = max(terms)
        log_cdf = peak + math.log(sum(math.exp(x-peak) for x in terms))
        if log_cdf > math.log(alpha):
            low = p
        else:
            high = p
    return high


def reasons(run):
    m, p = run['metrics'], run['profile']
    failures = [key for key in SAFETY_COUNTERS if m[key] != 0]
    if m['uas_requested'] == 0:
        failures.append('no_uas_measurement_cohort')
    if m['uas_completion_fraction'] is None or m['uas_completion_fraction'] < p['minimum_completion_fraction']:
        failures.append('uas_completion_requirement')
    if p['manned_operations_per_hour'] > 0:
        if m['manned_requested'] == 0:
            failures.append('no_manned_measurement_cohort')
        if m['manned_completion_fraction'] is None or m['manned_completion_fraction'] < p['minimum_completion_fraction']:
            failures.append('manned_completion_requirement')
        if p['manned_detection_fraction'] < 1:
            failures.append('incomplete_manned_surveillance_assumption')
    if m['p95_uas_wait_s'] is None or m['p95_uas_wait_s'] > p['maximum_p95_wait_s']:
        failures.append('queue_wait_requirement')
    if m['backlog_growth'] > p['maximum_backlog_growth']:
        failures.append('backlog_growth_requirement')
    return failures


def summarize(runs, expected_profiles, rates, limits, seeds):
    if not runs or not expected_profiles or not rates or not limits or not seeds:
        raise ValueError('A complete, nonempty campaign is required')
    profile_ids = {identity(asdict(p)): p for p in expected_profiles}
    if len(profile_ids) != len(expected_profiles):
        raise ValueError('Duplicate operating profiles')
    expected = {(pid, rate, limit, seed) for pid in profile_ids for rate in rates for limit in limits for seed in seeds}
    actual = [(identity(r['profile']), r['uas_demand_per_hour'], r['occupancy_limit'], r['seed']) for r in runs]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError('Missing, duplicate or unexpected campaign rows')
    # All tested cells share a family-wise error budget. The same seeds may be
    # paired across cells; independence is required within each cell only.
    cells = len(profile_ids)*len(rates)*len(limits)
    rows = []
    for pid, profile in profile_ids.items():
        alpha = (1-profile.confidence)/cells
        for rate in sorted(rates):
            for limit in sorted(limits):
                group = [r for r in runs if identity(r['profile']) == pid and r['uas_demand_per_hour'] == rate and r['occupancy_limit'] == limit]
                violations = [reasons(r) for r in group]
                failure_count = sum(any(r['metrics'][k] for k in SAFETY_COUNTERS) for r in group)
                bound = upper_failure_probability(failure_count, len(group), alpha)
                blockers = sorted({reason for row in violations for reason in row})
                if bound > profile.failure_probability_per_run:
                    evidence_blockers = ['insufficient_statistical_safety_evidence']
                else:
                    evidence_blockers = []
                rows.append(dict(profile_id=pid, profile_name=profile.name, scenario=profile.scenario,
                                 uas_demand_per_hour=rate, occupancy_limit=limit, independent_runs=len(group),
                                 total_demand_per_hour=rate+profile.manned_operations_per_hour,
                                 modeled_safety_failure_runs=failure_count, failure_probability_upper=bound,
                                 failure_probability_target=profile.failure_probability_per_run,
                                 observed_requirements_pass=not blockers,
                                 statistical_requirements_pass=not blockers and not evidence_blockers,
                                 blockers=blockers + evidence_blockers,
                                 observed_uas_throughput_min_per_hour=min(r['metrics']['uas_completed_per_hour'] for r in group),
                                 observed_manned_throughput_min_per_hour=min(r['metrics']['manned_completed_per_hour'] for r in group),
                                 observed_total_throughput_min_per_hour=min(r['metrics']['uas_completed_per_hour']+r['metrics']['manned_completed_per_hour'] for r in group),
                                 observed_peak_total_occupancy=max(r['metrics']['peak_total_occupancy'] for r in group),
                                 observed_peak_uas_occupancy=max(r['metrics']['peak_uas_occupancy'] for r in group),
                                 worst_command_max_ms=max(r['metrics']['command_max_ms'] for r in group),
                                 zero_failure_runs_required=math.ceil(math.log(alpha)/math.log1p(-profile.failure_probability_per_run))))
    envelope = []
    for rate in sorted(rates):
        for limit in sorted(limits):
            matching = [r for r in rows if r['uas_demand_per_hour'] == rate and r['occupancy_limit'] == limit]
            envelope.append(dict(uas_demand_per_hour=rate, occupancy_limit=limit,
                                 observed_requirements_pass=all(r['observed_requirements_pass'] for r in matching),
                                 statistical_requirements_pass=all(r['statistical_requirements_pass'] for r in matching)))
    observed = [r for r in envelope if r['observed_requirements_pass']]
    supported = [r for r in envelope if r['statistical_requirements_pass']]
    per_profile = []
    for pid in profile_ids:
        observed_cells = [r for r in rows if r['profile_id'] == pid and r['observed_requirements_pass']]
        supported_cells = [r for r in observed_cells if r['statistical_requirements_pass']]
        per_profile.append(dict(profile_id=pid,
            highest_observed_passing_total_demand_per_hour=max((r['total_demand_per_hour'] for r in observed_cells), default=None),
            highest_statistically_supported_tested_total_demand_per_hour=max((r['total_demand_per_hour'] for r in supported_cells), default=None),
            highest_supported_observed_concurrent_aircraft=max((r['observed_peak_total_occupancy'] for r in supported_cells), default=None)))
    return dict(schema='federated-swarm.airspace-capacity.v1',
                capacity_unit='UAS offered operations/hour conditional on declared manned demand and requirements',
                maximum_observed_passing_uas_demand_per_hour=max((r['uas_demand_per_hour'] for r in observed), default=None),
                maximum_statistically_supported_tested_uas_demand_per_hour=max((r['uas_demand_per_hour'] for r in supported), default=None),
                operationally_certified_capacity=None,
                maximum_is_only_over_tested_grid=True, per_profile_capacity=per_profile, envelope=envelope, cells=rows,
                limits=[
                    'Null capacity means no positive demonstrated value; it does not establish that physical capacity is zero.',
                    'No monotonicity assumption, binary search or interpolation between tested levels.',
                    'Statistical bound concerns independent fixed-duration scenario runs, not failures per flight/hour.',
                    'All supplied profiles are required; favorable scenarios cannot offset a failing profile.',
                    'Finite windows and backlog checks do not establish long-run queue stability.',
                    'Host timing and an explicit synthetic multiplier do not establish target hardware WCET.',
                    'Manned traffic uses simplified bounded trajectories; wake, ATC, pilot and aircraft flight models are absent.',
                    'Separation and surveillance thresholds are research inputs, not regulatory minima.',
                    'No joint invariant safety proof, field validation, airworthiness or legal authorization.'])


def render(summary):
    value = summary['maximum_observed_passing_uas_demand_per_hour']
    supported = summary['maximum_statistically_supported_tested_uas_demand_per_hour']
    lines = ['# Airspace capacity assessment', '',
             f'Highest tested demand passing observed requirements: **{value if value is not None else "not demonstrated"}** UAS operations/hour.',
             f'Statistically supported tested demand: **{supported if supported is not None else "not demonstrated"}** UAS operations/hour.',
             'Operationally certified capacity: **not established**.', '',
             '| Profile / scenario | UAS demand/h | Occupancy limit | Runs | UAS exits/h (worst) | Manned exits/h (worst) | Peak total | Observed pass | Failure upper bound | Blocking requirements |',
             '|---|---:|---:|---:|---:|---:|---:|---|---:|---|']
    for r in summary['cells']:
        lines.append(f"| {r['profile_name']} / {r['scenario']} | {r['uas_demand_per_hour']:g} | {r['occupancy_limit']} | {r['independent_runs']} | {r['observed_uas_throughput_min_per_hour']:.1f} | {r['observed_manned_throughput_min_per_hour']:.1f} | {r['observed_peak_total_occupancy']} | {r['observed_requirements_pass']} | {r['failure_probability_upper']:.4f} | {', '.join(r['blockers'])} |")
    lines.extend(['', *['- '+x for x in summary['limits']], ''])
    return '\n'.join(lines)
