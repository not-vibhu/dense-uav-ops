from dense_uav_ops.config import from_dict


def small(**sections):
    """A short experiment for tests: 10 s warmup, 30 s window, 20 s drain."""
    document = {'window': {'warmup_s': 10., 'measurement_s': 30., 'drain_s': 20.}}
    for key, value in sections.items():
        if isinstance(value, dict):
            document[key] = {**document.get(key, {}), **value}
        else:
            document[key] = value
    return from_dict(document).validate()
