# Steward Shift

A shift scheduling optimizer that uses linear programming (PuLP) to assign
employees to shifts while respecting constraints like vacations, part-time
schedules, team distributions, and consecutive shift limits.

## Features

- **Daily staffing requirements** - Configure different staffing needs per day
  of week
- **Fair distribution** - Shifts are distributed proportionally based on
  availability and team distribution
- **Team distribution targets** - Set percentage targets for how shifts are
  split between teams
- **Part-time support** - Employees can specify which days they're available
- **Vacation handling** - Multiple vacation periods per employee, including
  single-day vacations
- **Team days** - Designate days when specific teams don't work (e.g. team has
  a day in the week when they coordinate, thus should not be considered for the
  shift)
- **Consecutive shift limits** - Prevent too many shifts in a row
- **Weekly shift limits** - Prefer max N shifts per week
- **Day rotation** - Prevent same person working same day-of-week in consecutive
  weeks (denoted as "same day violation")
- **CSV export** - Export schedules in matrix format for Excel/Google Sheets

## Installation

```bash
# Install dependencies
uv sync

# Run the CLI
steward-shift config/mgb_config.yaml
```

## Usage

```bash
# Full report with all details
steward-shift config/schedule.yaml

# Minimal output (schedule only)
steward-shift config/schedule.yaml --quiet

# Export to CSV
steward-shift config/schedule.yaml --export-csv output.csv
```


## Configuration

Configuration is done via YAML. See `config/example_config.yaml` for a complete
example.

```yaml
planning:
  start_date: 2026-01-01
  duration_weeks: 12

staffing_requirements:
  monday: 3
  tuesday: 2
  wednesday: 2
  thursday: 2
  friday: 2
  saturday: 0
  sunday: 0

teams:
  Engineering:
    target_percentage: 0.6
    team_day: 2  # Wednesday - no Engineering staff works
  Support:
    target_percentage: 0.4
    team_day: 3  # Thursday

employees:
  - name: Alice
    team: Engineering
    available_days: [0, 1, 2, 3, 4]  # Mon-Fri (full-time)
    vacations:
      - start: 2026-02-02
        end: 2026-02-06
  - name: Bob
    team: Support
    available_days: [0, 2, 4]  # Mon, Wed, Fri (part-time)

penalties:
  team_deviation: 10000  # High = near-hard constraint
  consecutive_shifts: 50  # Moderate = soft constraint
  weekly_shifts: 30  # Penalty for exceeding max shifts per week
  same_day_consecutive_weeks: 10  # Penalty for same day in back-to-back weeks

constraints:
  max_consecutive_shifts: 3  # Penalize working more than 3 days in a row
  max_shifts_per_week: 1  # Ideal max shifts per week
  prevent_same_day_consecutive_weeks: true  # Rotate day-of-week assignments
```

### Key Configuration Options

| Option                                        | Description                                        |
|-----------------------------------------------|----------------------------------------------------|
| `planning.start_date`                         | Date (YYYY-MM-DD)                                  |
| `planning.duration_weeks`                     | Number of weeks to schedule                        |
| `staffing_requirements`                       | People needed per day of week                      |
| `teams.*.target_percentage`                   | Must sum to 1.0                                    |
| `teams.*.team_day`                            | Day index (0=Mon, 6=Sun) when team doesn't work    |
| `employees.*.available_days`                  | List of day indices employee can work              |
| `constraints.max_consecutive_shifts`          | Max consecutive days before penalty applies        |
| `constraints.max_shifts_per_week`             | Ideal max shifts per week (soft)                   |
| `constraints.prevent_same_day_consecutive_weeks` | Penalize same day-of-week in back-to-back weeks |


## CSV Export

The `--export-csv` flag exports the schedule in a matrix format optimized for
Excel and Google Sheets:

```csv
Employee,2026-01-05 Mon,2026-01-06 Tue,2026-01-07 Wed
--- Engineering ---,,,
Alice,X,,X
Bob,,X,
--- Support ---,,,
Carol,X,,
Dan,,X,X
TOTAL,=COUNTIF(B2:B6,"X"),=COUNTIF(C2:C6,"X"),=COUNTIF(D2:D6,"X")
```


| Employee            | 2026-01-05 Mon      | 2026-01-06 Tue      | 2026-01-07 Wed      |
|---------------------|---------------------|---------------------|---------------------|
| --- Engineering --- |                     |                     |                     |
| Alice               | X                   |                     | X                   |
| Bob                 |                     | X                   |                     |
| --- Support ---     |                     |                     |                     |
| Carol               | X                   |                     |                     |
| Dan                 |                     | X                   | X                   |
|---------------------|---------------------|---------------------|---------------------|
| TOTAL               | =COUNTIF(B2:B6,"X") | =COUNTIF(C2:C6,"X") | =COUNTIF(D2:D6,"X") |


### Format Features

| Feature                  | Description                                |
|--------------------------|--------------------------------------------|
| **Matrix layout**        | Employees as rows, dates as columns        |
| **Team grouping**        | Employees grouped by team with header rows |
| **Alphabetical sorting** | Employees sorted A-Z within each team      |
| **Shift markers**        | `X` indicates an assigned shift            |
| **TOTAL row**            | Excel COUNTIF formulas for column sums     |


## Development

```bash
# Install in editable mode
uv sync

# Run tests
uv run pytest

# Run single test
uv run pytest tests/test_file.py::test_name

# Build package
uv build
```

## Mathematical Model

The optimizer uses PuLP to solve a Mixed Integer Linear Program (MILP).

### Sets and Indices

| Symbol | Description |
|--------|-------------|
| $E$ | Set of employees |
| $T$ | Set of teams |
| $D = \{0, 1, \ldots, n-1\}$ | Set of days in planning period |
| $W = \{0, 1, \ldots, w-1\}$ | Set of weeks |
| $i \in E$ | Employee index |
| $t \in T$ | Team index |
| $k \in D$ | Day index |
| $w \in W$ | Week index |

### Parameters

| Symbol | Description |
|--------|-------------|
| $A_{ik}$ | Availability: 1 if employee $i$ can work on day $k$, 0 otherwise |
| $r_k$ | Required staff on day $k$ |
| $p_t$ | Target percentage for team $t$ (must sum to 1) |
| $\hat{S}_i$ | Ideal shifts for employee $i$ (calculated from availability) |
| $M$ | Total shifts required: $M = \sum_{k \in D} r_k$ |
| $\kappa$ | Max consecutive shifts before penalty |
| $\mu$ | Max weekly shifts before penalty |
| $\alpha$ | Penalty weight for team deviation |
| $\beta$ | Penalty weight for consecutive shifts |
| $\gamma$ | Penalty weight for weekly excess |
| $\delta$ | Penalty weight for same-day consecutive weeks |

### Decision Variables

| Variable | Domain | Description |
|----------|--------|-------------|
| $x_{ik}$ | $\{0, 1\}$ | 1 if employee $i$ works on day $k$ |
| $S_i$ | $\mathbb{Z}^+$ | Total shifts assigned to employee $i$ |
| $S_t$ | $\mathbb{R}^+$ | Total shifts assigned to team $t$ |
| $D_t$ | $\mathbb{R}^+$ | Absolute deviation from team target |
| $Z_i$ | $\mathbb{R}^+$ | Absolute deviation from ideal shifts for employee $i$ |
| $C_{ik}$ | $\{0, 1\}$ | 1 if consecutive violation starts at day $k$ for employee $i$ |
| $W_{iw}$ | $\mathbb{Z}^+$ | Excess shifts above max in week $w$ for employee $i$ |
| $R_{iwd}$ | $\{0, 1\}$ | 1 if employee $i$ works day-of-week $d$ in both weeks $w$ and $w+1$ |

### Objective Function

$$\min \sum_{i \in E} Z_i + \alpha \sum_{t \in T} D_t + \beta \sum_{i \in E} \sum_{k \in D} C_{ik} + \gamma \sum_{i \in E} \sum_{w \in W} W_{iw} + \delta \sum_{i \in E} \sum_{w=0}^{|W|-2} \sum_{d=0}^{6} R_{iwd}$$

### Hard Constraints

**Staffing requirements** — exactly $r_k$ employees must work each day:

$$\sum_{i \in E} x_{ik} = r_k \quad \forall k \in D$$

**Availability** — employees can only work when available:

$$x_{ik} = 0 \quad \forall i \in E, k \in D : A_{ik} = 0$$

**Shift counting** — link assignments to totals:

$$S_i = \sum_{k \in D} x_{ik} \quad \forall i \in E$$

$$S_t = \sum_{i \in E_t} S_i \quad \forall t \in T$$

where $E_t$ is the set of employees in team $t$.

### Soft Constraints (Penalized)

**Fairness** — minimize deviation from ideal shifts:

$$Z_i \geq \hat{S}_i - S_i \quad \forall i \in E$$
$$Z_i \geq S_i - \hat{S}_i \quad \forall i \in E$$

**Team distribution** — minimize deviation from target percentages:

$$D_t \geq p_t \cdot M - S_t \quad \forall t \in T$$
$$D_t \geq S_t - p_t \cdot M \quad \forall t \in T$$

**Consecutive shifts** — detect when $\kappa + 1$ consecutive days are worked:

$$C_{ik} \geq \sum_{j=0}^{\kappa} x_{i,k+j} - \kappa \quad \forall i \in E, k \in D : k + \kappa < n$$

**Weekly shifts** — capture excess above maximum per week:

$$W_{iw} \geq \sum_{k=7w}^{7w+6} x_{ik} - \mu \quad \forall i \in E, w \in W$$

**Same-day consecutive weeks** — detect same day-of-week in back-to-back weeks:

$$R_{iwd} \geq x_{i,7w+d} + x_{i,7(w+1)+d} - 1 \quad \forall i \in E, w \in \{0, \ldots, |W|-2\}, d \in \{0, \ldots, 6\}$$

### Ideal Shifts Calculation

The ideal shifts $\hat{S}_i$ for employee $i$ in team $t$ is calculated as:

$$\hat{S}_i = \frac{\text{availableDays}_i}{\sum_{j \in E_t} \text{availableDays}_j} \cdot p_t \cdot M$$

This distributes the team's target shifts proportionally based on each employee's availability.

### Soft Constraints Summary

| Constraint | What it prevents | Default | Penalty |
|------------|------------------|---------|---------|
| Consecutive shifts | Working > $\kappa$ days in a row | $\kappa = 3$ | $\beta = 50$ |
| Weekly shifts | Working > $\mu$ times per week | $\mu = 1$ | $\gamma = 30$ |
| Same-day consecutive weeks | Same weekday two weeks in a row | enabled | $\delta = 10$ |
| Team deviation | Missing team percentage targets | — | $\alpha = 10000$ |

Higher penalty values make constraints stricter. Set penalty to 0 to disable.

---

## Notes

- For a shift we have a certain number of people we need to reach for a day
  (e.g. on monday 3 people meed to do that shift, rest of the week only 2
  persons are needed).
- Some employees have vacations we want to be able to specify. Multiple
  vacations per person per period are possible. One day vacations are also
  possible.
- Some employees are only part time here. Part time should be taken into
  account, such that they do less that shift.
- There are two teams are doing that shift, team A should do 67% of all shifts,
  team B should do 33% of all shifts (these distributions should be variable).
- The shifts should be distributed equally among all employees, according to
  the team membership.
- It is not feasible for a person to do more than `k` shifts in a row. This is
  modeled as a soft boundary. `k` is set in the conifg file.
- We want to be able to plan for a specified period of time. (set in config)



- Max 1x per week
  - If 2 days, then not consecutive
- not same person always mondays and not always fridays
- If fridays, not monday
- teamdays: members of a certain team should not have shift on that teamday

- output as csv
  - like a calendar
  - modular, s.t. we can push to teams
