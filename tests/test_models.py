"""Tests for data models."""

import pytest
from datetime import date

from steward_shift.models import VacationPeriod, Employee, Team, ScheduleConfig


class TestVacationPeriod:
    """Tests for VacationPeriod validation and behavior."""

    def test_end_before_start_raises_error(self):
        """Vacation end date cannot be before start date."""
        with pytest.raises(ValueError, match="cannot be before start date"):
            VacationPeriod(start=date(2026, 1, 10), end=date(2026, 1, 5))

    def test_same_day_vacation_is_valid(self):
        """Single-day vacation (start == end) is valid."""
        vac = VacationPeriod(start=date(2026, 1, 5), end=date(2026, 1, 5))
        assert vac.duration_days == 1

    @pytest.mark.parametrize(
        "check_date,expected",
        [
            (date(2026, 1, 4), False),  # Before
            (date(2026, 1, 5), True),  # Start
            (date(2026, 1, 7), True),  # Middle
            (date(2026, 1, 10), True),  # End
            (date(2026, 1, 11), False),  # After
        ],
    )
    def test_contains_checks_date_boundaries(self, check_date: date, expected: bool):
        """Vacation contains() correctly checks inclusive boundaries."""
        vac = VacationPeriod(start=date(2026, 1, 5), end=date(2026, 1, 10))
        assert vac.contains(check_date) == expected

    def test_duration_is_inclusive(self):
        """Duration includes both start and end days."""
        vac = VacationPeriod(start=date(2026, 1, 5), end=date(2026, 1, 9))
        assert vac.duration_days == 5  # Mon-Fri


class TestTeam:
    """Tests for Team validation."""

    @pytest.mark.parametrize("invalid_percentage", [-0.1, 1.1, 2.0])
    def test_invalid_percentage_raises_error(self, invalid_percentage: float):
        """Target percentage must be between 0 and 1."""
        with pytest.raises(ValueError, match="between 0 and 1"):
            Team(name="Test", target_percentage=invalid_percentage)

    @pytest.mark.parametrize("valid_percentage", [0.0, 0.5, 1.0])
    def test_valid_percentage_accepted(self, valid_percentage: float):
        """Boundary percentages are valid."""
        team = Team(name="Test", target_percentage=valid_percentage)
        assert team.target_percentage == valid_percentage

    @pytest.mark.parametrize("invalid_day", [-1, 7, 10])
    def test_invalid_team_day_raises_error(self, invalid_day: int):
        """Team day must be 0-6."""
        with pytest.raises(ValueError, match="between 0.*and 6"):
            Team(name="Test", target_percentage=0.5, team_day=invalid_day)

    @pytest.mark.parametrize("day,is_team_day", [(0, True), (1, False), (6, False)])
    def test_is_team_day(self, day: int, is_team_day: bool):
        """is_team_day correctly identifies the designated day."""
        team = Team(name="Test", target_percentage=0.5, team_day=0)
        assert team.is_team_day(day) == is_team_day

    def test_no_team_day_never_matches(self):
        """Team without team_day returns False for all days."""
        team = Team(name="Test", target_percentage=0.5, team_day=None)
        assert all(not team.is_team_day(d) for d in range(7))


class TestEmployee:
    """Tests for Employee availability logic."""

    def test_is_available_on_weekday(self, full_time_employee: Employee):
        """Full-time employee available Mon-Fri."""
        assert full_time_employee.is_available_on_weekday(0)  # Monday
        assert full_time_employee.is_available_on_weekday(4)  # Friday
        assert not full_time_employee.is_available_on_weekday(5)  # Saturday
        assert not full_time_employee.is_available_on_weekday(6)  # Sunday

    def test_part_time_availability(self, part_time_employee: Employee):
        """Part-time employee only available on specified days."""
        assert part_time_employee.is_available_on_weekday(0)  # Monday
        assert not part_time_employee.is_available_on_weekday(1)  # Tuesday
        assert part_time_employee.is_available_on_weekday(2)  # Wednesday

    def test_vacation_blocks_availability(self, employee_with_vacation: Employee):
        """Employee is unavailable during vacation."""
        # During vacation (Jan 5-9, 2026)
        assert employee_with_vacation.is_on_vacation(date(2026, 1, 7))
        assert not employee_with_vacation.is_available_on_date(date(2026, 1, 7), 2)

        # Not on vacation
        assert not employee_with_vacation.is_on_vacation(date(2026, 1, 12))
        assert employee_with_vacation.is_available_on_date(date(2026, 1, 12), 0)

    def test_multiple_vacations(self):
        """Employee can have multiple vacation periods."""
        emp = Employee(
            name="Test",
            team="TeamA",
            available_days=[0, 1, 2, 3, 4],
            vacations=[
                VacationPeriod(start=date(2026, 1, 5), end=date(2026, 1, 9)),
                VacationPeriod(start=date(2026, 2, 1), end=date(2026, 2, 5)),
            ],
        )
        assert emp.is_on_vacation(date(2026, 1, 7))
        assert emp.is_on_vacation(date(2026, 2, 3))
        assert not emp.is_on_vacation(date(2026, 1, 20))


class TestScheduleConfig:
    """Tests for ScheduleConfig calculations."""

    def test_total_days_calculation(self, minimal_config: ScheduleConfig):
        """Total days equals weeks * 7."""
        assert minimal_config.total_days == 7

    def test_team_names_property(self, minimal_config: ScheduleConfig):
        """team_names returns list of all team names."""
        assert set(minimal_config.team_names) == {"TeamA", "TeamB"}

    def test_get_team_returns_correct_team(self, minimal_config: ScheduleConfig):
        """get_team finds team by name."""
        team = minimal_config.get_team("TeamA")
        assert team.name == "TeamA"
        assert team.target_percentage == 0.6

    def test_get_team_raises_for_unknown(self, minimal_config: ScheduleConfig):
        """get_team raises ValueError for unknown team."""
        with pytest.raises(ValueError, match="not found"):
            minimal_config.get_team("NonExistent")

    def test_employees_in_team(self, minimal_config: ScheduleConfig):
        """employees_in_team filters correctly."""
        team_a = minimal_config.employees_in_team("TeamA")
        assert len(team_a) == 2
        assert all(emp.team == "TeamA" for emp in team_a)

    def test_default_max_consecutive_shifts(self):
        """Default max_consecutive_shifts is 3."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={i: 0 for i in range(7)},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[Employee(name="E", team="T", available_days=[0])],
        )
        assert config.max_consecutive_shifts == 3

    def test_custom_max_consecutive_shifts(self):
        """max_consecutive_shifts can be customized."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={i: 0 for i in range(7)},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[Employee(name="E", team="T", available_days=[0])],
            max_consecutive_shifts=5,
        )
        assert config.max_consecutive_shifts == 5
