"""Shared fixtures for steward-shift tests."""

import pytest
from datetime import date

from steward_shift.models import (
    Employee,
    Team,
    VacationPeriod,
    ScheduleConfig,
)


@pytest.fixture
def simple_team() -> Team:
    """A basic team with 50% target."""
    return Team(name="TeamA", target_percentage=0.5)


@pytest.fixture
def team_with_team_day() -> Team:
    """A team with a designated team day (Wednesday)."""
    return Team(name="TeamB", target_percentage=0.5, team_day=2)


@pytest.fixture
def full_time_employee() -> Employee:
    """Full-time employee available Mon-Fri."""
    return Employee(
        name="Alice",
        team="TeamA",
        available_days=[0, 1, 2, 3, 4],
    )


@pytest.fixture
def part_time_employee() -> Employee:
    """Part-time employee available Mon, Wed, Fri."""
    return Employee(
        name="Bob",
        team="TeamA",
        available_days=[0, 2, 4],
    )


@pytest.fixture
def employee_with_vacation() -> Employee:
    """Employee with a vacation period."""
    return Employee(
        name="Carol",
        team="TeamA",
        available_days=[0, 1, 2, 3, 4],
        vacations=[VacationPeriod(start=date(2026, 1, 5), end=date(2026, 1, 9))],
    )


@pytest.fixture
def minimal_config() -> ScheduleConfig:
    """Minimal valid config for testing optimization."""
    return ScheduleConfig(
        start_date=date(2026, 1, 5),  # Monday
        duration_weeks=1,
        staffing_requirements={
            0: 1,  # Mon
            1: 1,  # Tue
            2: 1,  # Wed
            3: 1,  # Thu
            4: 1,  # Fri
            5: 0,  # Sat
            6: 0,  # Sun
        },
        teams=[
            Team(name="TeamA", target_percentage=0.6),
            Team(name="TeamB", target_percentage=0.4),
        ],
        employees=[
            Employee(name="Alice", team="TeamA", available_days=[0, 1, 2, 3, 4]),
            Employee(name="Bob", team="TeamA", available_days=[0, 1, 2, 3, 4]),
            Employee(name="Carol", team="TeamB", available_days=[0, 1, 2, 3, 4]),
        ],
    )


@pytest.fixture
def config_with_vacations() -> ScheduleConfig:
    """Config with employee vacations."""
    return ScheduleConfig(
        start_date=date(2026, 1, 5),  # Monday
        duration_weeks=2,
        staffing_requirements={
            0: 1,
            1: 1,
            2: 1,
            3: 1,
            4: 1,
            5: 0,
            6: 0,
        },
        teams=[
            Team(name="TeamA", target_percentage=1.0),
        ],
        employees=[
            Employee(
                name="Alice",
                team="TeamA",
                available_days=[0, 1, 2, 3, 4],
                vacations=[
                    VacationPeriod(start=date(2026, 1, 5), end=date(2026, 1, 9))
                ],
            ),
            Employee(name="Bob", team="TeamA", available_days=[0, 1, 2, 3, 4]),
        ],
    )


@pytest.fixture
def config_with_team_days() -> ScheduleConfig:
    """Config where teams have designated off-days."""
    return ScheduleConfig(
        start_date=date(2026, 1, 5),  # Monday
        duration_weeks=1,
        staffing_requirements={
            0: 1,
            1: 1,
            2: 1,
            3: 1,
            4: 1,
            5: 0,
            6: 0,
        },
        teams=[
            Team(name="TeamA", target_percentage=0.5, team_day=0),  # Off Monday
            Team(name="TeamB", target_percentage=0.5, team_day=4),  # Off Friday
        ],
        employees=[
            Employee(name="Alice", team="TeamA", available_days=[0, 1, 2, 3, 4]),
            Employee(name="Bob", team="TeamB", available_days=[0, 1, 2, 3, 4]),
        ],
    )
