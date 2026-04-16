"""
REAL VERIFICATION #3: Panjer Parameters vs Claimed ES Values  [PARTIAL]

Verifies: severity distribution characteristics (mean, tail shape) for the
three categories with fully specified parameters.
Does NOT verify: the actual compound ES values (0.34M, 0.88M, 3.12M) because
the frequency model parameters are insufficiently specified for two categories,
and the compound convolution depends on truncation/discretization choices not
stated in the whitepaper.

Doc 3 gives specific distributions per operational risk category:
  - Oracle manipulation: LogNormal(mu=13.1, sigma=1.55) severity => ES = 0.34M
  - Smart contract bug: Pareto(alpha=1.41, x_min=50k) severity => ES = 0.88M
  - Exchange insolvency: freq=0.9/yr, Recovery-Beta(6,4)*TVL severity => ES = 3.12M
  - Regulatory shutdown: 2-state Markov freq [UNDERSPECIFIED] => ES = 0.48M
  - Key management failure: Threshold compound [UNDERSPECIFIED] => ES = 0.29M
"""
import numpy as np
from scipy import stats
import pytest


class TestOracleManipulationES:
    """Oracle manipulation: LogNormal(mu=13.1, sigma=1.55) severity.
    Check if the 99.9% ES is plausibly ~0.34M."""

    def test_lognormal_es_order_of_magnitude(self):
        """Monte Carlo ES for LogNormal(13.1, 1.55)."""
        rng = np.random.default_rng(42)
        mu, sigma = 13.1, 1.55
        n_sims = 1_000_000

        # Single-event severity in USD
        severities = rng.lognormal(mu, sigma, n_sims)

        # ES at 99.9%
        var_999 = np.quantile(severities, 0.999)
        es_999 = severities[severities >= var_999].mean()

        # Convert to millions
        es_m = es_999 / 1e6

        # Document claims Panjer ES_99.9 = 0.34M
        # This is a compound (frequency * severity) ES, not single-event ES.
        # Single-event median = exp(13.1) ~ 485k, mean = exp(13.1 + 1.55^2/2) ~ 1.6M
        single_mean = np.exp(mu + sigma**2 / 2)
        print(f"Single-event mean: ${single_mean/1e6:.2f}M")
        print(f"Single-event 99.9% VaR: ${var_999/1e6:.2f}M")
        print(f"Single-event 99.9% ES: ${es_m:.2f}M")

        # The compound ES depends on frequency. With low frequency, the
        # compound ES is much lower than single-event ES.
        # We can at least verify the severity distribution is sensible.
        assert single_mean > 100_000, "Mean severity should be > $100k"
        assert single_mean < 100_000_000, "Mean severity should be < $100M"


class TestExchangeInsolvencyES:
    """Exchange insolvency: freq=0.9/yr, Recovery-Beta(6,4)*TVL.
    Check if compound ES is plausibly ~3.12M."""

    def test_compound_es(self):
        """Monte Carlo compound distribution."""
        rng = np.random.default_rng(42)
        lam = 0.9  # Poisson rate per year
        TVL = 100e6  # $100M TVL baseline (from Doc 3 Section 6.3)
        n_sims = 500_000

        annual_losses = np.zeros(n_sims)
        for i in range(n_sims):
            n_events = rng.poisson(lam)
            if n_events > 0:
                # Recovery ~ Beta(6, 4), so Loss = (1 - Recovery) * TVL
                recoveries = rng.beta(6, 4, n_events)
                losses = (1 - recoveries) * TVL
                annual_losses[i] = losses.sum()

        # ES at 99.9%
        var_999 = np.quantile(annual_losses, 0.999)
        tail = annual_losses[annual_losses >= var_999]
        es_999 = tail.mean() / 1e6  # in millions

        print(f"Exchange insolvency compound ES_99.9: ${es_999:.2f}M")
        print(f"Document claims: $3.12M")

        # The claim is 3.12M. Check order of magnitude.
        # Expected annual loss = 0.9 * E[1-Recovery] * TVL = 0.9 * 0.4 * 100M = 36M
        # Wait, that's the EXPECTED loss, not the tail.
        # E[Recovery] for Beta(6,4) = 6/10 = 0.6, so E[Loss fraction] = 0.4
        expected_annual = lam * 0.4 * TVL / 1e6
        print(f"Expected annual loss: ${expected_annual:.2f}M")

        # 3.12M is way below the expected annual loss of 36M.
        # This suggests either TVL is much smaller, or the claim is wrong,
        # or "ES" here means something different (per-event, not annual).
        assert es_999 > 1.0, "ES should be at least $1M"


class TestSmartContractBugES:
    """Smart contract bug: Pareto(alpha=1.41, x_min=50k).
    Check ES characteristics."""

    def test_pareto_es(self):
        """Verify Pareto tail behavior and ES computation."""
        alpha_param = 1.41
        x_min = 50_000  # $50k

        rng = np.random.default_rng(42)
        n_sims = 1_000_000

        # Pareto distribution: P(X > x) = (x_min/x)^alpha for x >= x_min
        severities = (rng.pareto(alpha_param, n_sims) + 1) * x_min

        # For Pareto with alpha > 1, mean = alpha * x_min / (alpha - 1)
        theoretical_mean = alpha_param * x_min / (alpha_param - 1)
        empirical_mean = severities.mean()
        assert abs(empirical_mean - theoretical_mean) / theoretical_mean < 0.02

        # ES at 99.9%
        var_999 = np.quantile(severities, 0.999)
        es_999 = severities[severities >= var_999].mean()

        print(f"Pareto single-event mean: ${theoretical_mean/1e3:.1f}k")
        print(f"Pareto 99.9% ES: ${es_999/1e6:.2f}M")

        # alpha = 1.41 < 2 means infinite variance — very heavy tail
        # The tail ES will be quite large relative to the mean
        assert es_999 > var_999, "ES must exceed VaR"
