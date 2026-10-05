"""Exact interval estimates used in campaign summaries (no SciPy dependency).

Units matter. A run is the independent replicate; aircraft and time steps within
a run are dependent. Event-rate intervals computed from pooled counts assume
independent events and are therefore optimistic when events cluster within
runs; summaries report the per-run spread alongside them.
"""
import math


def _bisect(f, low, high, iterations=200):
    """Root of a monotone function on [low, high]."""
    f_low = f(low)
    for _ in range(iterations):
        mid = (low + high) / 2
        if (f(mid) > 0) == (f_low > 0):
            low, f_low = mid, f(mid)
        else:
            high = mid
    return (low + high) / 2


def _log_binomial_cdf(k, n, p):
    if k < 0:
        return -math.inf
    if k >= n or p <= 0:
        return 0.
    if p >= 1:
        return -math.inf
    terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log1p(-p)
             for i in range(k + 1)]
    peak = max(terms)
    return peak + math.log(sum(math.exp(t - peak) for t in terms))


def clopper_pearson(k, n, confidence=.95):
    """Exact two-sided interval for a binomial proportion k/n."""
    if n <= 0 or not 0 <= k <= n:
        raise ValueError('need 0 <= k <= n and n > 0')
    alpha = 1 - confidence
    lower = 0. if k == 0 else _bisect(lambda p: (1 - math.exp(_log_binomial_cdf(k - 1, n, p))) - alpha / 2, 0., 1.)
    upper = 1. if k == n else _bisect(lambda p: math.exp(_log_binomial_cdf(k, n, p)) - alpha / 2, 0., 1.)
    return lower, upper


def _log_poisson_cdf(k, mu):
    if k < 0:
        return -math.inf
    if mu <= 0:
        return 0.
    terms = [i * math.log(mu) - mu - math.lgamma(i + 1) for i in range(k + 1)]
    peak = max(terms)
    return peak + math.log(sum(math.exp(t - peak) for t in terms))


def poisson_interval(k, confidence=.95):
    """Exact (Garwood) two-sided interval for a Poisson mean given k observed events."""
    if k < 0:
        raise ValueError('k must be nonnegative')
    alpha = 1 - confidence
    high = 10. + 10. * k
    lower = 0. if k == 0 else _bisect(lambda mu: (1 - math.exp(_log_poisson_cdf(k - 1, mu))) - alpha / 2, 0., high)
    upper = _bisect(lambda mu: math.exp(_log_poisson_cdf(k, mu)) - alpha / 2, 0., high)
    return lower, upper


def rate(events, exposure_hours, confidence=.95):
    """Events per hour with a Poisson interval that assumes independent events."""
    if exposure_hours <= 0:
        return {'per_hour': None, 'interval_if_independent': None, 'events': events, 'hours': exposure_hours}
    low, high = poisson_interval(events, confidence)
    return {'per_hour': events / exposure_hours,
            'interval_if_independent': [low / exposure_hours, high / exposure_hours],
            'events': events, 'hours': exposure_hours}
