"""Tests for the shift optimizer."""

import pytest
from datetime import date

from steward_shift.models import Employee, Team, ScheduleConfig, VacationPeriod
from steward_shift.optimizer import ShiftOptimizer


class TestOptimizerBasics:
    """Basic optimization tests."""

    def test_finds_optimal_solution(self, minimal_config: ScheduleConfig):
        """Optimizer finds an optimal solution for valid config."""
        optimizer = ShiftOptimizer(minimal_config)
        result = optimizer.optimize()

        assert result.is_optimal
        assert result.status == "Optimal"

    def test_meets_daily_staffing_requirements(self, minimal_config: ScheduleConfig):
        """Each day has exactly the required number of staff."""
        result = ShiftOptimizer(minimal_config).optimize()

        for assignment in result.daily_assignments:
            assert assignment.actual == assignment.required

    def test_total_shifts_equals_sum_of_requirements(
        self, minimal_config: ScheduleConfig
    ):
        """Total shifts required matches sum of daily requirements."""
        result = ShiftOptimizer(minimal_config).optimize()

        expected_total = sum(minimal_config.staffing_requirements.values())
        assert result.total_shifts_required == expected_total


class TestAvailabilityConstraints:
    """Tests for employee availability constraints."""

    def test_vacation_days_not_assigned(self, config_with_vacations: ScheduleConfig):
        """Employees are not assigned shifts during vacation."""
        result = ShiftOptimizer(config_with_vacations).optimize()

        alice_schedule = result.get_employee_schedule("Alice")

        # Alice is on vacation days 0-4 (Mon-Fri of week 1)
        # She should only be assigned in week 2
        for day_idx in alice_schedule.assigned_days:
            assert day_idx >= 7, f"Alice assigned on day {day_idx} during vacation"

    def test_team_day_not_assigned(self, config_with_team_days: ScheduleConfig):
        """Employees not assigned on their team's designated off-day."""
        result = ShiftOptimizer(config_with_team_days).optimize()

        # Alice (TeamA) should not work Monday (day 0)
        alice_schedule = result.get_employee_schedule("Alice")
        assert 0 not in alice_schedule.assigned_days

        # Bob (TeamB) should not work Friday (day 4)
        bob_schedule = result.get_employee_schedule("Bob")
        assert 4 not in bob_schedule.assigned_days

    def test_part_time_only_assigned_available_days(self):
        """Part-time employees only assigned on their available days."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=1,
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                # Only available Mon, Wed, Fri
                Employee(name="PartTimer", team="T", available_days=[0, 2, 4]),
                # Full-time backup
                Employee(name="FullTimer", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
        )
        result = ShiftOptimizer(config).optimize()

        part_timer = result.get_employee_schedule("PartTimer")
        # PartTimer can only be assigned to days 0, 2, 4 (Mon, Wed, Fri)
        for day_idx in part_timer.assigned_days:
            day_of_week = day_idx % 7
            assert day_of_week in [0, 2, 4]


class TestTeamDistribution:
    """Tests for team percentage distribution."""

    def test_team_distribution_respected(self):
        """Team shift distribution approximates target percentages."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 2, 1: 2, 2: 2, 3: 2, 4: 2, 5: 0, 6: 0},
            teams=[
                Team(name="TeamA", target_percentage=0.6),
                Team(name="TeamB", target_percentage=0.4),
            ],
            employees=[
                Employee(name="A1", team="TeamA", available_days=[0, 1, 2, 3, 4]),
                Employee(name="A2", team="TeamA", available_days=[0, 1, 2, 3, 4]),
                Employee(name="A3", team="TeamA", available_days=[0, 1, 2, 3, 4]),
                Employee(name="B1", team="TeamB", available_days=[0, 1, 2, 3, 4]),
                Employee(name="B2", team="TeamB", available_days=[0, 1, 2, 3, 4]),
            ],
        )
        result = ShiftOptimizer(config).optimize()

        team_a_summary = next(
            ts for ts in result.team_summaries if ts.team.name == "TeamA"
        )
        team_b_summary = next(
            ts for ts in result.team_summaries if ts.team.name == "TeamB"
        )

        total = result.total_shifts_required
        team_a_pct = team_a_summary.actual_shifts / total
        team_b_pct = team_b_summary.actual_shifts / total

        # Allow some deviation due to integer constraints
        assert 0.5 <= team_a_pct <= 0.7, f"TeamA got {team_a_pct:.0%}, expected ~60%"
        assert 0.3 <= team_b_pct <= 0.5, f"TeamB got {team_b_pct:.0%}, expected ~40%"


class TestConsecutiveShiftConstraint:
    """Tests for consecutive shift soft constraint."""

    @pytest.mark.parametrize("max_consecutive", [1, 2, 3, 4, 5])
    def test_max_consecutive_is_configurable(self, max_consecutive: int):
        """Different max_consecutive_shifts values are applied."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E2", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
            max_consecutive_shifts=max_consecutive,
        )
        result = ShiftOptimizer(config).optimize()

        assert result.is_optimal
        assert result.config.max_consecutive_shifts == max_consecutive

    def test_consecutive_violations_counted_correctly(self):
        """Violations are counted when consecutive exceeds max."""
        # Create scenario where one employee must work many consecutive days
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                # Only one employee - must work all 5 days
                Employee(name="Solo", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
            max_consecutive_shifts=2,  # Low limit to force violations
        )
        result = ShiftOptimizer(config).optimize()

        solo = result.get_employee_schedule("Solo")
        # Working 5 consecutive days with max=2 means violations
        assert solo.actual_shifts == 5
        assert solo.max_consecutive == 5
        assert solo.consecutive_violations > 0


class TestFairnessObjective:
    """Tests for fair shift distribution among employees."""

    def test_shifts_distributed_fairly(self):
        """Shifts are distributed fairly among equally available employees."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 2, 1: 2, 2: 2, 3: 2, 4: 2, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E2", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E3", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E4", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
        )
        result = ShiftOptimizer(config).optimize()

        shifts = [es.actual_shifts for es in result.employee_schedules]

        # 20 total shifts / 4 employees = 5 each ideally
        # Allow ±1 deviation due to integer constraints
        assert all(4 <= s <= 6 for s in shifts), f"Unfair distribution: {shifts}"

    def test_ideal_shifts_reflects_availability(self):
        """Ideal shifts are calculated proportionally to availability."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 2, 1: 2, 2: 2, 3: 2, 4: 2, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                # Full-time (5 days/week = 10 available days)
                Employee(name="FullTime", team="T", available_days=[0, 1, 2, 3, 4]),
                # Part-time (2 days/week = 4 available days)
                Employee(name="PartTime", team="T", available_days=[0, 4]),
            ],
        )
        result = ShiftOptimizer(config).optimize()

        full_time = result.get_employee_schedule("FullTime")
        part_time = result.get_employee_schedule("PartTime")

        # Ideal shifts should be proportional to availability
        # FullTime: 10 available, PartTime: 4 available
        # So ideal ratio should be roughly 10:4 = 2.5:1
        assert full_time.ideal_shifts > part_time.ideal_shifts
        ratio = full_time.ideal_shifts / part_time.ideal_shifts
        assert 2.0 <= ratio <= 3.0, f"Expected ratio ~2.5, got {ratio:.2f}"


class TestWeeklyShiftConstraint:
    """Tests for weekly shift soft constraint."""

    @pytest.mark.parametrize("max_weekly", [1, 2, 3, 4, 5])
    def test_max_weekly_is_configurable(self, max_weekly: int):
        """Different max_shifts_per_week values are applied."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E2", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
            max_shifts_per_week=max_weekly,
        )
        result = ShiftOptimizer(config).optimize()

        assert result.is_optimal
        assert result.config.max_shifts_per_week == max_weekly

    def test_weekly_shifts_tracked_per_week(self):
        """Weekly shifts list has correct length and values."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=3,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Solo", team="T", available_days=[0]),
            ],
            max_shifts_per_week=1,
        )
        result = ShiftOptimizer(config).optimize()

        solo = result.get_employee_schedule("Solo")
        # 3 weeks, 1 shift per week (Monday only)
        assert len(solo.weekly_shifts) == 3
        assert solo.weekly_shifts == [1, 1, 1]
        assert solo.weekly_violations == 0

    def test_weekly_violations_counted_correctly(self):
        """Violations are counted when weekly shifts exceed max."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                # Only one employee - must work all 5 days in the week
                Employee(name="Solo", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
            max_shifts_per_week=2,  # Low limit to force violations
        )
        result = ShiftOptimizer(config).optimize()

        solo = result.get_employee_schedule("Solo")
        assert solo.weekly_shifts == [5]
        assert solo.weekly_violations == 1
        assert solo.max_weekly_shifts == 5

    def test_weekly_constraint_influences_distribution(self):
        """With low max_shifts_per_week, shifts spread across employees."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E2", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E3", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E4", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E5", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
            max_shifts_per_week=1,
            penalty_weekly_shifts=1000,  # High penalty to enforce constraint
        )
        result = ShiftOptimizer(config).optimize()

        # With 5 employees and 5 shifts, max_weekly=1 should spread evenly
        for emp_sched in result.employee_schedules:
            assert emp_sched.max_weekly_shifts <= 1


class TestSameDayConsecutiveWeeksConstraint:
    """Tests for same day consecutive weeks soft constraint."""

    def test_constraint_enabled_by_default(self):
        """Constraint is enabled by default."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0]),
            ],
        )
        assert config.prevent_same_day_consecutive_weeks is True

    def test_constraint_can_be_disabled(self):
        """Constraint can be disabled via config."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=False,
        )
        result = ShiftOptimizer(config).optimize()
        assert result.is_optimal

    def test_violations_counted_correctly(self):
        """Violations are counted when same day in consecutive weeks."""
        # One employee available only on Monday - must work Monday both weeks
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Solo", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=True,
        )
        result = ShiftOptimizer(config).optimize()

        solo = result.get_employee_schedule("Solo")
        # Must work Monday both weeks = 1 violation
        assert solo.same_day_consecutive_weeks_violations == 1

    def test_no_violations_when_different_days(self):
        """No violations when working different days each week."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0, 1]),
                Employee(name="E2", team="T", available_days=[0, 1]),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=1000,  # High penalty
        )
        result = ShiftOptimizer(config).optimize()

        # With high penalty and enough employees, should avoid same-day violations
        total_violations = sum(
            es.same_day_consecutive_weeks_violations for es in result.employee_schedules
        )
        assert total_violations == 0

    def test_constraint_influences_assignment(self):
        """With high penalty, optimizer avoids same-day consecutive weeks."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0]),
                Employee(name="E2", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=1000,
        )
        result = ShiftOptimizer(config).optimize()

        # With 2 employees available Monday, optimizer should assign different
        # employee each week to avoid same-day violation
        e1 = result.get_employee_schedule("E1")
        e2 = result.get_employee_schedule("E2")

        # Each should work exactly 1 Monday (not the same person both weeks)
        assert e1.actual_shifts == 1
        assert e2.actual_shifts == 1

    def test_single_week_no_violations(self):
        """Single week schedules have no same-day consecutive week violations."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Solo", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
            prevent_same_day_consecutive_weeks=True,
        )
        result = ShiftOptimizer(config).optimize()

        solo = result.get_employee_schedule("Solo")
        assert solo.same_day_consecutive_weeks_violations == 0

    def test_disabled_constraint_allows_same_day_assignments(self):
        """When disabled, optimizer freely assigns same day in consecutive weeks."""
        # Two employees, but E1 is preferred due to higher availability
        # With constraint disabled, optimizer may assign same person both weeks
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Solo", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=False,
        )
        optimizer = ShiftOptimizer(config)

        # Verify R variables are not created when constraint is disabled
        assert optimizer.R is None

        result = optimizer.optimize()
        assert result.is_optimal

        # Solo must work both Mondays (only person available)
        solo = result.get_employee_schedule("Solo")
        assert solo.actual_shifts == 2
        assert 0 in solo.assigned_days  # Week 1 Monday
        assert 7 in solo.assigned_days  # Week 2 Monday
        # Violations still counted for reporting, but no penalty applied
        assert solo.same_day_consecutive_weeks_violations == 1

    def test_rotation_when_multiple_employees_available(self):
        """With 2 employees for 1 Monday slot, they should alternate weeks."""
        # This is the key test: when rotation IS possible, it MUST happen
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Alice", team="T", available_days=[0]),
                Employee(name="Bob", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=10000,  # Very high penalty
        )
        result = ShiftOptimizer(config).optimize()

        alice = result.get_employee_schedule("Alice")
        bob = result.get_employee_schedule("Bob")

        # Each should work exactly 1 shift (rotation)
        assert alice.actual_shifts == 1
        assert bob.actual_shifts == 1

        # No violations - they alternated
        assert alice.same_day_consecutive_weeks_violations == 0
        assert bob.same_day_consecutive_weeks_violations == 0

        # Verify they work different weeks
        alice_days = set(alice.assigned_days)
        bob_days = set(bob.assigned_days)
        assert alice_days.isdisjoint(bob_days)

    def test_forced_violation_when_no_alternative(self):
        """When only one employee is available, violation is unavoidable."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                # Only Alice available on Monday
                Employee(name="Alice", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=10000,
        )
        result = ShiftOptimizer(config).optimize()

        alice = result.get_employee_schedule("Alice")

        # Must work both Mondays - no choice
        assert alice.actual_shifts == 2
        assert 0 in alice.assigned_days  # Week 1 Monday
        assert 7 in alice.assigned_days  # Week 2 Monday
        assert alice.same_day_consecutive_weeks_violations == 1

    def test_three_week_rotation(self):
        """With 3 weeks and 3 employees, each works once with no violations."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=3,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Alice", team="T", available_days=[0]),
                Employee(name="Bob", team="T", available_days=[0]),
                Employee(name="Carol", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=10000,
        )
        result = ShiftOptimizer(config).optimize()

        # Each works exactly 1 Monday
        for emp_sched in result.employee_schedules:
            assert emp_sched.actual_shifts == 1
            assert emp_sched.same_day_consecutive_weeks_violations == 0

        # All three Mondays are covered by different people
        all_assigned = []
        for emp_sched in result.employee_schedules:
            all_assigned.extend(emp_sched.assigned_days)
        assert sorted(all_assigned) == [0, 7, 14]  # Mon week 1, 2, 3

    def test_three_weeks_two_employees_no_violation_possible(self):
        """With 3 weeks and 2 employees, alternating pattern avoids violations."""
        # Pattern A-B-A or B-A-B means no consecutive weeks with same person
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=3,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Alice", team="T", available_days=[0]),
                Employee(name="Bob", team="T", available_days=[0]),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=10000,
        )
        result = ShiftOptimizer(config).optimize()

        total_violations = sum(
            es.same_day_consecutive_weeks_violations for es in result.employee_schedules
        )

        # Pattern A-B-A means: week1-week2 different, week2-week3 different
        # No consecutive weeks have the same person!
        assert total_violations == 0

        # Verify shifts: one person works twice, the other once
        shifts = [es.actual_shifts for es in result.employee_schedules]
        assert sorted(shifts) == [1, 2]

    def test_forced_consecutive_violation_via_vacation(self):
        """Vacation in middle week forces same person to work consecutive weeks."""
        # Week 1: Alice or Bob available
        # Week 2: Only Alice available (Bob on vacation)
        # Week 3: Only Alice available (Bob on vacation)
        # Alice must work weeks 2 and 3 = 1 violation
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=3,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Alice", team="T", available_days=[0]),
                Employee(
                    name="Bob",
                    team="T",
                    available_days=[0],
                    # Bob on vacation weeks 2 and 3 (Mon Jan 12 and Mon Jan 19)
                    vacations=[
                        VacationPeriod(start=date(2026, 1, 12), end=date(2026, 1, 19))
                    ],
                ),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=10000,
        )
        result = ShiftOptimizer(config).optimize()

        alice = result.get_employee_schedule("Alice")
        bob = result.get_employee_schedule("Bob")

        # Bob works week 1 (only week he's available)
        assert bob.actual_shifts == 1
        assert 0 in bob.assigned_days

        # Alice must work weeks 2 and 3
        assert alice.actual_shifts == 2
        assert 7 in alice.assigned_days  # Week 2 Monday
        assert 14 in alice.assigned_days  # Week 3 Monday

        # Alice has 1 violation (same day weeks 2 and 3)
        assert alice.same_day_consecutive_weeks_violations == 1
        assert bob.same_day_consecutive_weeks_violations == 0

    def test_independent_days_dont_interfere(self):
        """Violations on Monday don't affect Tuesday rotation."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                # Alice only available Monday - forced violation
                Employee(name="Alice", team="T", available_days=[0]),
                # Bob and Carol available Tuesday - can rotate
                Employee(name="Bob", team="T", available_days=[1]),
                Employee(name="Carol", team="T", available_days=[1]),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=10000,
        )
        result = ShiftOptimizer(config).optimize()

        alice = result.get_employee_schedule("Alice")
        bob = result.get_employee_schedule("Bob")
        carol = result.get_employee_schedule("Carol")

        # Alice has forced Monday violation
        assert alice.same_day_consecutive_weeks_violations == 1

        # Bob and Carol rotate Tuesdays - no violations
        assert bob.same_day_consecutive_weeks_violations == 0
        assert carol.same_day_consecutive_weeks_violations == 0
        assert bob.actual_shifts == 1
        assert carol.actual_shifts == 1

    def test_partial_availability_prevents_rotation(self):
        """Employee unavailable in week 2 forces same-day assignment."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),  # Monday
            duration_weeks=2,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Alice", team="T", available_days=[0]),
                # Bob is on vacation week 2 (Mon Jan 12)
                Employee(
                    name="Bob",
                    team="T",
                    available_days=[0],
                    vacations=[
                        VacationPeriod(start=date(2026, 1, 12), end=date(2026, 1, 18))
                    ],
                ),
            ],
            prevent_same_day_consecutive_weeks=True,
            penalty_same_day_consecutive_weeks=10000,
        )
        result = ShiftOptimizer(config).optimize()

        # Bob works week 1, Alice must work week 2 (Bob on vacation)
        # If Bob works week 1 and Alice works week 2, no violation
        # (different people on same day = no violation)
        total_violations = sum(
            es.same_day_consecutive_weeks_violations for es in result.employee_schedules
        )
        # Should be 0 - Bob week 1, Alice week 2 (different people)
        assert total_violations == 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_staffing_days_handled(self):
        """Days with zero staffing requirement have no assignments."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={
                0: 1,
                1: 0,  # No one needed Tuesday
                2: 1,
                3: 0,  # No one needed Thursday
                4: 1,
                5: 0,
                6: 0,
            },
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
        )
        result = ShiftOptimizer(config).optimize()

        for assignment in result.daily_assignments:
            if assignment.required == 0:
                assert len(assignment.employees) == 0

    def test_single_employee_single_day(self):
        """Minimal case: one employee, one day."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={0: 1, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="Solo", team="T", available_days=[0]),
            ],
        )
        result = ShiftOptimizer(config).optimize()

        assert result.is_optimal
        assert result.total_shifts_required == 1
        solo = result.get_employee_schedule("Solo")
        assert solo.actual_shifts == 1
