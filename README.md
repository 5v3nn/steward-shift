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

## How It Works

The optimizer uses PuLP to solve a linear programming problem that:

1. **Minimizes** deviation from ideal shift distribution + team target
   penalties + consecutive shift penalties + weekly shift penalties +
   same-day-consecutive-week penalties
2. **Subject to:**
   - Daily staffing requirements are met exactly
   - Employees only assigned when available (respects part-time, vacations,
     team days)
   - Team shift totals approximate target percentages

### Soft Constraints

The following are **soft constraints** (penalized, not forbidden):

| Constraint                 | What it prevents                       | Default    |
|----------------------------|----------------------------------------|------------|
| Consecutive shifts         | Working too many days in a row         | max 3      |
| Weekly shifts              | Working too often in one week          | max 1/week |
| Same day consecutive weeks | Working e.g. Monday two weeks in a row | enabled    |

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
