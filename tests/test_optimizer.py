"""Tests for the shift optimizer."""

import pytest
from datetime import date

from steward_shift.models import Employee, Team, ScheduleConfig
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
        assert solo.violations_count > 0


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
