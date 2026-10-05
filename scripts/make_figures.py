"""Figures and tables for docs/report from committed evidence.

Inputs: experiments/frontier-01/summary.json and docs/report/data/history.json
(run scripts/reanalyze_history.py first). Outputs: docs/report/figures/*.png and
docs/report/data/frontier-01-table.md. Requires the `analysis` extra (matplotlib).

Usage: python scripts/make_figures.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / 'docs/report/figures'
DATA = ROOT / 'docs/report/data'

# Validated with the dataviz palette checker: blue ordinal ramp for the assumed acceleration
# (magnitude), categorical orange and aqua for the two baselines; markers give a second channel.
SURFACE, INK, MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e2dc'
RAMP = {'predictive-A0': '#86b6ef', 'predictive-A1': '#3987e5', 'predictive-A2': '#1c5cab', 'predictive-A4': '#0d366b'}
ARMS = {'none': ('No avoidance', '#eb6834', 'X'), 'daidalus': ('DAIDALUS bands', '#1baf7a', 'D'),
        **{k: (f'Planner, assumed A = {k[-1]} m/s²', v, 'o') for k, v in RAMP.items()}}
ORDER = ['none', 'daidalus', 'predictive-A0', 'predictive-A1', 'predictive-A2', 'predictive-A4']

plt.rcParams.update({
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
    'axes.edgecolor': GRID, 'axes.labelcolor': INK, 'text.color': INK, 'xtick.color': MUTED, 'ytick.color': MUTED,
    'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': .8, 'axes.spines.top': False, 'axes.spines.right': False,
    'font.size': 9, 'axes.titlesize': 9.5, 'axes.titleweight': 'bold', 'legend.frameon': False,
    'lines.linewidth': 2, 'lines.solid_capstyle': 'round', 'lines.solid_joinstyle': 'round', 'lines.markersize': 5.5})


def save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / name, dpi=200, bbox_inches='tight')
    plt.close(fig)


def enclosure_figure():
    """Assumed reachable radius around a 0.5 s-old report, plus the 10 m separation."""
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    ts = [i / 20 for i in range(0, 101)]
    for a, key in zip((0, 1, 2, 4), RAMP):
        r = [1.5 + .3 * (.5 + t) + .5 * a * (.5 + t) ** 2 + 10 for t in ts]
        ax.plot(ts, r, color=RAMP[key], label=f'A = {a} m/s²')
        ax.annotate(f'{r[48]:.0f} m', (2.4, r[48]), xytext=(4, 0), textcoords='offset points', va='center', fontsize=8, color=MUTED)
    ax.axvline(2.4, color=MUTED, linewidth=1)
    ax.text(2.42, 2, 'planning horizon 2.4 s', color=MUTED, fontsize=8)
    ax.set_xlabel('look-ahead time (s)')
    ax.set_ylabel('protected radius around a neighbour (m)')
    ax.set_ylim(0, None)
    ax.legend(loc='upper left')
    ax.set_title('Protected radius around a 0.5 s-old report (incl. 10 m separation)')
    save(fig, 'enclosure-radius.png')


def history_figures(history):
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    names = {'goal': ('Direct goal flight', '#eb6834', 'X'), 'repulsion': ('Repulsion', '#e87ba4', 's'),
             'barrier': ('Barrier filter', '#2a78d6', 'o'), 'negotiated': ('Barrier + negotiation', '#4a3aa7', '^')}
    sizes = [10, 50, 100, 200]
    for key, (label, color, marker) in names.items():
        rows = history['iteration_01']['collision_run_rate_by_fleet_size'][key]
        ax.plot(sizes, [100 * rows[str(s)]['collision_run_rate'] for s in sizes], color=color, marker=marker, label=label)
    ax.set_xscale('log')
    ax.set_xticks(sizes, [str(s) for s in sizes])
    ax.minorticks_off()
    ax.set_xlabel('aircraft in the encounter')
    ax.set_ylabel('holdout runs with a participant collision (%)')
    ax.set_ylim(0, 105)
    ax.legend(loc='lower right')
    ax.set_title('Iteration 01: the run-level indicator saturates with fleet size')
    save(fig, 'history-iteration01-saturation.png')

    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    series = {'All demand enters': (['off', 'scale-off'], '#0d366b', 'o'), 'Checked entry': (['checked', 'scale-checked'], '#86b6ef', 's')}
    for label, (campaigns, color, marker) in series.items():
        points = sorted((int(size), row['failed_library_fraction'] * 100)
                        for c in campaigns for size, row in history['iteration_03']['predictive_by_fleet_size'][c].items())
        ax.plot([p[0] for p in points], [p[1] for p in points], color=color, marker=marker, label=label)
    ax.set_xscale('log')
    ax.set_xticks([10, 50, 100, 200], ['10', '50', '100', '200'])
    ax.minorticks_off()
    ax.set_xlabel('aircraft requested')
    ax.set_ylabel('steps with no admissible maneuver (%)')
    ax.set_ylim(0, 100)
    ax.legend(loc='upper left')
    ax.set_title('Iteration 03: under worst-case assumptions the planner runs out of options')
    save(fig, 'history-iteration03-failed-library.png')


def cells_by(summary):
    out = {}
    for c in summary['cells']:
        cell = c['cell']
        out[(cell['arm'], cell['surveillance.latency_s'], cell['fleet.cooperative_fraction'], cell['demand.uas_per_hour'])] = c
    return out


def facet_figure(summary, name, title, y, ylabel, ylim=None, logy=False):
    cells = cells_by(summary)
    latencies = sorted({k[1] for k in cells})
    equipage = sorted({k[2] for k in cells}, reverse=True)
    demands = sorted({k[3] for k in cells})
    fig, axes = plt.subplots(len(equipage), len(latencies), figsize=(7.4, 5.6), sharex=True, sharey=True)
    for r, eq in enumerate(equipage):
        for col, lat in enumerate(latencies):
            ax = axes[r][col]
            for arm in ORDER:
                xs, ys = [], []
                for d in demands:
                    value = y(cells[(arm, lat, eq, d)])
                    if value is not None:
                        xs.append(d)
                        ys.append(value)
                label, color, marker = ARMS[arm]
                if xs:
                    ax.plot(xs, ys, color=color, marker=marker, label=label)
            ax.set_xscale('log')
            ax.set_xticks(demands, [f'{d:,}' for d in demands], rotation=0)
            ax.minorticks_off()
            if logy:
                ax.set_yscale('symlog', linthresh=1)
            if ylim:
                ax.set_ylim(*ylim)
            ax.set_title(f'{int(eq * 100)} % cooperative, latency {lat:g} s', fontweight='normal')
            if r == len(equipage) - 1:
                ax.set_xlabel('offered UAS operations per hour')
    fig.supylabel(ylabel, fontsize=9)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=3, bbox_to_anchor=(.5, -.06))
    fig.suptitle(title, fontweight='bold', fontsize=10)
    fig.tight_layout()
    save(fig, name)


def frontier_scatter(summary):
    """Risk per 1000 completed operations against delivered controlled throughput, one panel per facet."""
    cells = cells_by(summary)
    latencies = sorted({k[1] for k in cells})
    equipage = sorted({k[2] for k in cells}, reverse=True)
    demands = sorted({k[3] for k in cells})
    fig, axes = plt.subplots(len(equipage), len(latencies), figsize=(7.4, 5.6), sharey=True)
    for r, eq in enumerate(equipage):
        for col, lat in enumerate(latencies):
            ax = axes[r][col]
            for arm in ORDER:
                xs, ys = [], []
                for d in demands:
                    c = cells[(arm, lat, eq, d)]
                    value = c['attributable_uas_los_per_1000_completed']
                    if value is not None:
                        xs.append(c['controlled_throughput_per_hour'])
                        ys.append(value)
                label, color, marker = ARMS[arm]
                ax.plot(xs, ys, color=color, marker=marker, label=label)
            ax.set_yscale('symlog', linthresh=1)
            ax.set_title(f'{int(eq * 100)} % cooperative, latency {lat:g} s', fontweight='normal')
            if r == len(equipage) - 1:
                ax.set_xlabel('controlled operations completed per hour')
    fig.supylabel('in-flight attributable LoS per 1000 completed controlled operations', fontsize=9)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=3, bbox_to_anchor=(.5, -.06))
    fig.suptitle('frontier-01: separation risk against delivered service (lower right is better)', fontweight='bold', fontsize=10)
    fig.tight_layout()
    save(fig, 'frontier-01-tradeoff.png')


def table(summary):
    rows = ['| Arm | Latency s | Cooperative | Offered/h | Runs | Mean UAS airborne | Completed controlled/h | Completion | Mean delay lower bound s | Fallback | In-flight attributable LoS | per flight-h [95 % if independent] | per 1000 ops | In-flight attributable contacts | Entry-phase attributable LoS |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    f = lambda x, s='.2f': '—' if x is None else format(x, s)
    key = lambda c: (ORDER.index(c['cell']['arm']), c['cell']['surveillance.latency_s'], -c['cell']['fleet.cooperative_fraction'], c['cell']['demand.uas_per_hour'])
    for c in sorted(summary['cells'], key=key):
        cell, los = c['cell'], c['attributable_uas_los']
        interval = los['interval_if_independent']
        rows.append(f"| {cell['arm']} | {cell['surveillance.latency_s']:g} | {cell['fleet.cooperative_fraction']:g} | {cell['demand.uas_per_hour']:,} | {c['runs']} | "
                    f"{f(c['mean_uas_occupancy'], '.1f')} | {f(c['controlled_throughput_per_hour'], '.0f')} | {f(c['controlled_completion_fraction'])} | "
                    f"{f(c['mean_delay_lower_bound_s'], '.1f')} | {f(c['fallback_fraction'], '.3f')} | {los['events']} | "
                    f"{f(los['per_hour'], '.2f')} [{f(interval[0], '.2f') if interval else '—'}, {f(interval[1], '.2f') if interval else '—'}] | "
                    f"{f(c['attributable_uas_los_per_1000_completed'], '.1f')} | {c['attributable_uas_contacts']['events']} | {c['entry_phase_attributable_uas_los']} |")
    (DATA / 'frontier-01-table.md').write_text('\n'.join(rows) + '\n')


def capacity_illustration(summary):
    """Pre-registered example requirement: attributable UAS contact upper bound < 1 per controlled
    flight-hour (Poisson, independence assumed), completion >= 0.95, mean delay lower bound <= 30 s."""
    cells = cells_by(summary)
    latencies = sorted({k[1] for k in cells})
    equipage = sorted({k[2] for k in cells}, reverse=True)
    demands = sorted({k[3] for k in cells})
    rows = ['| Arm | ' + ' | '.join(f'{int(eq * 100)} % coop, {lat:g} s' for eq in equipage for lat in latencies) + ' |',
            '|---|' + '---|' * (len(equipage) * len(latencies))]
    detail = {}
    for arm in ORDER:
        entries = []
        for eq in equipage:
            for lat in latencies:
                passing, blockers = [], {}
                for d in demands:
                    c = cells[(arm, lat, eq, d)]
                    interval = c['attributable_uas_contacts']['interval_if_independent']
                    reasons = []
                    if interval is None or interval[1] >= 1.:
                        reasons.append('contact bound')
                    if (c['controlled_completion_fraction'] or 0.) < .95:
                        reasons.append('completion')
                    if (c['mean_delay_lower_bound_s'] or 0.) > 30.:
                        reasons.append('delay')
                    if not reasons:
                        passing.append(d)
                    blockers[d] = reasons
                entries.append(f'{max(passing):,}' if passing else 'not demonstrated')
                detail[f'{arm} {eq} {lat}'] = blockers
        rows.append(f'| {ARMS[arm][0]} | ' + ' | '.join(entries) + ' |')
    (DATA / 'frontier-01-capacity.md').write_text('\n'.join(rows) + '\n')
    (DATA / 'frontier-01-capacity-blockers.json').write_text(json.dumps(detail, indent=1) + '\n')


def stress_figures(summary):
    """frontier-02: risk and delay against the wander cap, per demand x noncompliant fraction."""
    cells = {(c['cell']['arm'], c['cell']['demand.uas_per_hour'], c['cell']['fleet.noncompliant_fraction'],
              c['cell']['fleet.noncompliant_acceleration_mps2']): c for c in summary['cells']}
    demands = sorted({k[1] for k in cells})
    fractions = sorted({k[2] for k in cells})
    caps = sorted({k[3] for k in cells})
    for name, title, value, label in (
            ('frontier-02-risk.png', 'frontier-02: in-flight attributable LoS when uncontrolled UAS wander',
             lambda c: c['attributable_uas_los_per_1000_completed'], 'in-flight attributable LoS per 1000 completed controlled operations'),
            ('frontier-02-delay.png', 'frontier-02: mean service delay when uncontrolled UAS wander',
             lambda c: c['mean_delay_lower_bound_s'], 'mean delay lower bound (s)')):
        fig, axes = plt.subplots(len(fractions), len(demands), figsize=(7.4, 5.6), sharex=True, sharey=True)
        for r, fraction in enumerate(fractions):
            for col, demand in enumerate(demands):
                ax = axes[r][col]
                for arm in ORDER:
                    xs = [cap for cap in caps if value(cells[(arm, demand, fraction, cap)]) is not None]
                    ys = [value(cells[(arm, demand, fraction, cap)]) for cap in xs]
                    lab, color, marker = ARMS[arm]
                    if xs:
                        ax.plot(xs, ys, color=color, marker=marker, label=lab)
                ax.set_yscale('symlog', linthresh=1)
                ax.set_xticks(caps, [f'{c:g}' for c in caps])
                ax.set_title(f'{demand:,} ops/h offered, {int(fraction * 100)} % noncompliant', fontweight='normal')
                if r == len(fractions) - 1:
                    ax.set_xlabel('noncompliant lateral acceleration cap (m/s²)')
        fig.supylabel(label, fontsize=9)
        handles, labels = axes[0][0].get_legend_handles_labels()
        fig.legend(handles, labels, loc='lower center', ncol=3, bbox_to_anchor=(.5, -.06))
        fig.suptitle(title, fontweight='bold', fontsize=10)
        fig.tight_layout()
        save(fig, name)
    rows = ['| Arm | Offered/h | Noncompliant | Wander cap m/s² | Completion | Mean delay lower bound s | Fallback | In-flight attributable LoS (cc / cu) | per 1000 ops | In-flight contacts | Entry-phase LoS |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    f = lambda x, spec='.2f': '—' if x is None else format(x, spec)
    for key in sorted(cells, key=lambda k: (ORDER.index(k[0]), k[1], k[2], k[3])):
        c = cells[key]
        rows.append(f"| {key[0]} | {key[1]:,} | {key[2]:g} | {key[3]:g} | {f(c['controlled_completion_fraction'])} | "
                    f"{f(c['mean_delay_lower_bound_s'], '.1f')} | {f(c['fallback_fraction'], '.3f')} | {c['attributable_uas_los']['events']} "
                    f"({c['los_by_category']['cc']} / {c['los_by_category']['cu']}) | {f(c['attributable_uas_los_per_1000_completed'], '.1f')} | "
                    f"{c['attributable_uas_contacts']['events']} | {c['entry_phase_attributable_uas_los']} |")
    (DATA / 'frontier-02-table.md').write_text('\n'.join(rows) + '\n')


def main():
    enclosure_figure()
    history_figures(json.loads((DATA / 'history.json').read_text()))
    summary_path = ROOT / 'experiments/frontier-01/summary.json'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        frontier_scatter(summary)
        facet_figure(summary, 'frontier-01-delay.png', 'frontier-01: mean service delay (unfinished operations counted as lower bounds)',
                     lambda c: c['mean_delay_lower_bound_s'], 'mean delay lower bound (s)', logy=True)
        facet_figure(summary, 'frontier-01-los-rate.png', 'frontier-01: attributable losses of separation per controlled flight-hour',
                     lambda c: c['attributable_uas_los']['per_hour'], 'attributable LoS per flight-hour', logy=True)
        facet_figure(summary, 'frontier-01-fallback.png', 'frontier-01: planner steps with no admissible maneuver',
                     lambda c: None if c['fallback_fraction'] is None else 100 * c['fallback_fraction'], 'fallback steps (%)')
        table(summary)
        capacity_illustration(summary)
    stress_path = ROOT / 'experiments/frontier-02/summary.json'
    if stress_path.exists():
        stress_figures(json.loads(stress_path.read_text()))
    print(sorted(p.name for p in FIGURES.glob('*.png')))


if __name__ == '__main__':
    main()
