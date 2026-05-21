# Crypto Statistical Arbitrage — Methodology Reference

The math of crypto stat-arb falls into six questions that must be answered in
order. Each has a canonical "best" method and viable alternatives. This is the
methodology reference for the `quant_tool` toolkit; the
[mapping to the codebase](#mapping-to-the-codebase) at the end links each
question to the module that implements it.

---

## 1. Is this pair actually mean-reverting? — Cointegration

Two non-stationary price series $X_t, Y_t$ are **cointegrated** if there exists
a $\beta$ such that the spread $Z_t = Y_t - \beta X_t$ is stationary.
Stationarity of the spread is the mathematical foundation for "mean reversion" —
without it you are running a directional bet with extra steps.

### Engle-Granger two-step (best for pairs)

1. Regress $Y_t = \alpha + \beta X_t + \epsilon_t$ by OLS and take the
   residuals $\hat\epsilon_t$.
2. Apply the **Augmented Dickey-Fuller (ADF)** test to $\hat\epsilon_t$:

$$\Delta\hat\epsilon_t = \rho\,\hat\epsilon_{t-1} + \sum_{i=1}^{p}\gamma_i\,\Delta\hat\epsilon_{t-i} + u_t$$

Test $H_0: \rho = 0$ (a unit root is present → non-stationary). Rejecting $H_0$
means the pair is cointegrated. The lag count $p$ is typically chosen by AIC.

### Johansen test (best for baskets of 3+ assets)

Model the system as a vector error-correction model (VECM):

$$\Delta Y_t = \Pi Y_{t-1} + \sum_{i=1}^{p-1}\Gamma_i\,\Delta Y_{t-i} + \epsilon_t$$

The rank of $\Pi$ equals the number of independent cointegrating relationships.
Use the trace statistic or the maximum-eigenvalue statistic. For pairs,
Engle-Granger is sufficient and more interpretable.

> **Crypto-specific caveat.** Cointegration relationships in crypto decay far
> faster than in equities. Always test on **rolling windows** (e.g. a 60-day
> window, refit weekly), never the full sample. A pair cointegrated over two
> years but not in the last 30 days is dead.

---

## 2. How does the spread move? — Ornstein-Uhlenbeck process

The canonical model for a mean-reverting spread is the Ornstein-Uhlenbeck SDE:

$$dX_t = \theta(\mu - X_t)\,dt + \sigma\,dW_t$$

- $\mu$ — long-run mean
- $\theta > 0$ — rate of mean reversion (larger $\theta$ ⇒ faster pull to mean)
- $\sigma$ — instantaneous volatility
- $dW_t$ — Wiener increment

**Exact** discrete-time form (not an Euler approximation):

$$X_{t+\Delta t} = X_t e^{-\theta\Delta t} + \mu\left(1 - e^{-\theta\Delta t}\right) + \sigma\sqrt{\frac{1 - e^{-2\theta\Delta t}}{2\theta}}\;\eta_t,\qquad \eta_t \sim \mathcal{N}(0,1)$$

This is an **AR(1)** in disguise: $X_{t+1} = a + b X_t + \epsilon_t$ with
$b = e^{-\theta\Delta t}$. Fit it with OLS and back out the parameters:

$$\theta = -\frac{\ln b}{\Delta t},\qquad \mu = \frac{a}{1-b},\qquad \sigma = \sigma_\epsilon\sqrt{\frac{-2\ln b}{\Delta t\,(1-b^2)}}$$

The single most important number falls out of this — the **half-life** of mean
reversion:

$$\tau_{1/2} = \frac{\ln 2}{\theta}$$

This is the expected time for the spread to revert halfway to its mean. If the
half-life is longer than your acceptable holding period, abandon the pair. For
crypto stat-arb on hourly bars, half-lives of **4–48 hours** are workable.
Anything beyond a few days will die before it reverts — the underlying
correlation breaks first.

---

## 3. What is the right hedge ratio, right now? — Kalman filter

Static OLS $\beta$ is wrong by the time you trade it. Rolling OLS is laggy and
its window length is arbitrary. The **Kalman filter** treats $\beta$ as a latent
state evolving over time and updates it Bayesian-optimally each tick. This is
the single highest-impact piece of the entire system.

State-space formulation for a pair:

$$\text{State:}\quad \beta_t = \beta_{t-1} + w_t,\qquad w_t \sim \mathcal{N}(0, Q)$$

$$\text{Observation:}\quad Y_t = \beta_t X_t + v_t,\qquad v_t \sim \mathcal{N}(0, R)$$

$Q$ controls how fast $\beta$ can drift; $R$ is observation noise. Their ratio
$Q/R$ is the only real tuning knob.

**Predict step** (project the state forward):

$$\hat\beta_{t\mid t-1} = \hat\beta_{t-1\mid t-1}$$

$$P_{t\mid t-1} = P_{t-1\mid t-1} + Q$$

**Update step** (correct using the new observation):

$$K_t = \frac{P_{t\mid t-1}\,X_t}{X_t^2\,P_{t\mid t-1} + R}$$

$$\hat\beta_{t\mid t} = \hat\beta_{t\mid t-1} + K_t\left(Y_t - X_t\,\hat\beta_{t\mid t-1}\right)$$

$$P_{t\mid t} = (1 - K_t X_t)\,P_{t\mid t-1}$$

$K_t$ is the **Kalman gain** — a bigger $K$ means trust the new observation
more. The forecast error $e_t = Y_t - X_t\,\hat\beta_{t\mid t-1}$ **is** your
trade signal: the instantaneous spread under the optimal hedge ratio.
Standardise it by its forecast variance to get a tradable z-score:

$$z_t = \frac{e_t}{\sqrt{X_t^2\,P_{t\mid t-1} + R}}$$

**Tuning $Q/R$.** Estimate by EM (maximum likelihood) on historical data, or
pick by cross-validation against forward returns. For crypto pairs $Q/R$
typically lands in $10^{-4}$ to $10^{-6}$ — $\beta$ is reasonably stable but you
let it adapt. Setting $Q = 0$ recovers expanding-window OLS; $Q \to \infty$
gives a one-step memory. Everything interesting is in between.

**Why this beats rolling OLS.** Rolling OLS implicitly assumes $\beta$ is
constant within the window and unknown outside it. The Kalman filter explicitly
models $\beta$'s drift and weights past observations by an exponential decay
derived from $Q/R$, not chosen by hand.

---

## 4. When to enter and exit? — Bertram's optimal thresholds

Naive: enter at $z = \pm 2$, exit at $z = 0$. Better: Bertram's analytical
solution to the optimal stopping problem on an OU process. Given a transaction
cost $c$, choose an entry threshold $a$ and an exit threshold $m$ that maximise
expected return per unit time.

Let the spread be normalised, $z = (X - \mu)/\sigma$. The expected first-passage
time from $a$ to $m$ on an OU process is:

$$\mathbb{E}[\tau \mid a \to m] = \frac{1}{\theta}\sum_{k=0}^{\infty}\frac{(a\sqrt{2})^{2k+1} - (m\sqrt{2})^{2k+1}}{(2k+1)!!\,(2k+1)}$$

The expected profit per trade is $|a - m| - c$. The optimisation is then:

$$\max_{a,\,m}\;\frac{|a - m| - c}{\mathbb{E}[\tau \mid a \to m]}$$

For symmetric strategies with $m = 0$, the optimum $a^\*$ satisfies a
transcendental equation in $\theta$ and $c$ solved numerically. Going to wider
$a$ gives larger per-trade PnL but the expected wait grows super-linearly — you
lose to alpha decay.

> **Practical reality.** For crypto with 8–15 bps round-trip cost, the optimal
> $a^\*$ typically lands at $z \in [1.0, 1.5]$, not the textbook 2.0. Use
> Bertram as a theoretical anchor; in practice grid-search $a \in [0.5, 3.0]$ on
> a backtest and pick the value that maximises net Sharpe.

---

## 5. How much to bet? — Kelly with shrinkage

For a strategy with drift $\mu$ and variance $\sigma^2$ per unit time, the
continuous **Kelly fraction** is:

$$f^\* = \frac{\mu}{\sigma^2}$$

This maximises the long-run growth rate of log wealth. **Full Kelly is too
aggressive for any real strategy** — $\mu$ and $\sigma$ are estimated with
error, and full-Kelly drawdowns of 40–50% are typical. Standard practice is
**fractional Kelly**, $f = 0.25\,f^\*$ to $0.5\,f^\*$.

For a portfolio of $N$ pairs with expected-return vector $\boldsymbol\mu$ and
covariance $\Sigma$:

$$\mathbf{f}^\* = \Sigma^{-1}\boldsymbol\mu$$

The problem: in crypto, $\Sigma$ estimated from sample data is ill-conditioned.
Many pairs are near-collinear, $\Sigma^{-1}$ blows up, and you end up with huge
concentrated positions that have nothing to do with edge.

**Ledoit-Wolf shrinkage** is the fix:

$$\tilde\Sigma = (1 - \lambda)\hat\Sigma + \lambda\,F$$

where $F$ is a structured target (typically the diagonal of $\hat\Sigma$, or a
constant-correlation matrix) and $\lambda \in [0, 1]$ is chosen analytically to
minimise the expected Frobenius distance to the true $\Sigma$. The closed form
for $\lambda$ involves only sample moments. This is non-negotiable for
portfolios beyond a handful of pairs.

---

## 6. Finding pairs to begin with — distance metric + clustering

Brute-force testing all $N(N-1)/2$ pairs has a multiple-testing problem. With
500 coins you have 124,750 pairs; at $\alpha = 0.05$ you expect ~6,200 spurious
cointegration rejections by chance alone.

The principled pipeline:

**Step 1 — distance matrix.** Compute a pairwise distance on normalised
returns. Correlation distance is more robust than sum-of-squared-differences:

$$d(i, j) = \sqrt{2\,(1 - \rho_{ij})}$$

This is a proper metric (the triangle inequality holds), so any clustering
algorithm can use it.

**Step 2 — cluster.** DBSCAN or hierarchical clustering on the distance matrix
identifies groups of correlated assets without forcing a $k$. A typical crypto
universe collapses into 5–15 meaningful clusters (L1s, DeFi blue chips, memes…).

**Step 3 — cointegration within clusters only.** This drops the testing burden
by an order of magnitude or more.

**Step 4 — multiple-testing correction.** Apply the Benjamini-Hochberg FDR
procedure (preferred over Bonferroni, which is too conservative) to the
surviving p-values to control the false discovery rate at, e.g., 10%.

> **A more sophisticated alternative — PCA-residual cointegration.** Run PCA on
> the universe's returns and treat the first $k$ components as common factors.
> Test whether each asset's residual (its return minus the reconstruction from
> $k$ factors) is stationary. This finds assets cointegrated with a *basket*,
> not just a single counterpart — a richer search space than pairs.

---

## Summary of methods, ranked by importance

| Question | Best method | Alternative | Notes |
|---|---|---|---|
| Is the pair cointegrated? | Engle-Granger + ADF on rolling windows | Johansen (baskets) | Test rolling, not full sample |
| How does the spread move? | Ornstein-Uhlenbeck (fit via AR(1)) | Vasicek, CIR | Half-life is the key number |
| Hedge ratio in real time | Kalman filter | Rolling OLS, online ridge | Highest-impact ML piece |
| Entry/exit thresholds | Bertram + grid search | Fixed $\pm 2\sigma$ | Crypto optima are tighter |
| Position sizing | Fractional Kelly | Volatility targeting | Use 0.25–0.5 Kelly, not full |
| Portfolio covariance | Ledoit-Wolf shrinkage | Sample covariance | Non-negotiable beyond ~5 pairs |
| Pair discovery | Cluster → test → FDR-correct | Brute-force all pairs | Multiple-testing is real |

**The end-to-end chain:** cluster the universe → test cointegration within
clusters → fit OU and reject pairs whose half-life is too long → set up a Kalman
filter for the survivors → use Bertram-derived thresholds on the Kalman z-score
→ size with fractional Kelly under a Ledoit-Wolf-shrunk covariance.

---

## Mapping to the codebase

How each question is currently served by `quant_tool`, and what is still on the
roadmap:

| Question | Toolkit module | Status |
|---|---|---|
| 1. Cointegration | `strategy/pair_finder.py` — `cointegration_test` (Engle-Granger + ADF via `statsmodels`) | Implemented full-sample. **Roadmap:** rolling-window re-testing. |
| 2. OU process | `strategy/pair_finder.py` — `half_life` (AR(1) fit) | Half-life implemented. **Roadmap:** full $(\theta, \mu, \sigma)$ estimation. |
| 3. Kalman hedge | `ai/kalman_filter.py` — `KalmanHedge` | Implemented as a 2-state $[\beta, \alpha]$ filter with a near-frozen intercept, so a non-zero cointegrating intercept is handled without the intercept absorbing the spread. **Roadmap:** EM tuning of $Q/R$. |
| 4. Entry/exit | `strategy/signals.py` — `generate_positions` | Fixed z-score thresholds with a stop. **Roadmap:** Bertram thresholds + a backtest grid search. |
| 5. Position sizing | `risk/sizing.py` — `vol_target_multiplier` | Volatility targeting (the alternative). **Roadmap:** fractional Kelly + Ledoit-Wolf covariance. |
| 6. Pair discovery | `strategy/pair_finder.py` — `find_cointegrated_pairs` | Brute-force over all column pairs. **Roadmap:** correlation-distance clustering then Benjamini-Hochberg FDR. |
