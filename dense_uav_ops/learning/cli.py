"""Training subcommands. Torch is imported only when a neural command runs."""
from dataclasses import replace


def add_commands(sub, configurable):
    pref = sub.add_parser('train-preferences', help='cross-entropy search over planner preference weights')
    configurable(pref)
    pref.add_argument('--seeds', type=int, nargs='+', default=[9001, 9002])
    pref.add_argument('--population', type=int, default=6)
    pref.add_argument('--generations', type=int, default=2)
    pref.add_argument('--search-seed', type=int, default=42)
    pref.add_argument('--workers', type=int, default=1)
    pref.add_argument('--out', required=True)
    for method in ('imitation', 'mappo'):
        p = sub.add_parser(f'train-{method}', help=f'recurrent attention policy: {method}')
        configurable(p)
        p.add_argument('--seeds', type=int, nargs='+', default=list(range(9100, 9108)))
        p.add_argument('--episodes', type=int, default=8)
        p.add_argument('--epochs', type=int, default=12 if method == 'imitation' else 3)
        p.add_argument('--training-seed', type=int, default=42)
        p.add_argument('--initial', default='')
        p.add_argument('--out', required=True)
    graph = sub.add_parser('train-graph', help='federated imitation of the graph ranker over airspace domains')
    configurable(graph)
    graph.add_argument('--sides', type=float, nargs='+', default=[300., 400., 600.],
                       help='airspace side length of each federated domain')
    graph.add_argument('--rounds', type=int, default=3)
    graph.add_argument('--out', required=True)


def dispatch(args):
    from ..__main__ import experiment_from
    base = experiment_from(args)
    if base.controller.kind != 'predictive':
        base = replace(base, controller=replace(base.controller, kind='predictive'))
    if args.command == 'train-preferences':
        from .preferences import search
        if args.population < 4 or args.generations < 1:
            raise ValueError('population >= 4 and generations >= 1 required')
        profile = search(base, args.seeds, args.population, args.generations, args.search_seed, args.out, args.workers)
        print({'weights': profile['weights'], 'fitness': profile['fitness']})
    elif args.command in ('train-imitation', 'train-mappo'):
        from .recurrent import train
        if not 1 <= args.episodes <= 10000 or not 1 <= args.epochs <= 100:
            raise ValueError('invalid episode or epoch count')
        sha = train(base, args.command.removeprefix('train-'), args.seeds, args.episodes, args.epochs,
                    args.training_seed, args.out, args.initial or None)
        print({'checkpoint': args.out, 'sha256': sha})
    elif args.command == 'train-graph':
        from .graph import train
        if not 1 <= args.rounds <= 20:
            raise ValueError('rounds must be 1–20')
        domains = []
        for k, side in enumerate(args.sides):
            experiment = replace(base, airspace=replace(base.airspace, side_m=side))
            domains.append((experiment, [9200 + 10 * k, 9201 + 10 * k], [9300 + k]))
        train(domains, args.out, rounds=args.rounds)
