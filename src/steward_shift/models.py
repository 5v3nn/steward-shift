"""
Data models for the shift scheduling system.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Dict


@dataclass
class VacationPeriod:
    """Represents a vacation period for an employee."""

    start: date
    end: date

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError(
                f"End date {self.end} cannot be before start date {self.start}"
            )

    def contains(self, check_date: date) -> bool:
        """Check if a date falls within this vacation period."""
        return self.start <= check_date <= self.end

    @property
    def duration_days(self) -> int:
        """Number of days in this vacation period (inclusive)."""
        return (self.end - self.start).days + 1


@dataclass
class Employee:
    """Represents an employee with their availability and vacation schedule."""

    name: str
    team: str
    available_days: List[int]  # Day of week indices: 0=Mon, 6=Sun
    vacations: List[VacationPeriod] = field(default_factory=list)

    def is_available_on_weekday(self, day_of_week: int) -> bool:
        """Check if employee works on this day of the week (0=Mon, 6=Sun)."""
        return day_of_week in self.available_days

    def is_on_vacation(self, check_date: date) -> bool:
        """Check if employee is on vacation on a specific date."""
        return any(vac.contains(check_date) for vac in self.vacations)

    def is_available_on_date(self, check_date: date, day_of_week: int) -> bool:
        """Check if employee is available on a specific date."""
        return self.is_available_on_weekday(day_of_week) and not self.is_on_vacation(
            check_date
        )


@dataclass
class Team:
    """Represents a team with a target shift percentage."""

    name: str
    target_percentage: float
    team_day: int | None = None  # Day of week when team doesn't work (0=Mon, 6=Sun)

    def __post_init__(self):
        if not 0 <= self.target_percentage <= 1:
            raise ValueError(
                f"Target percentage must be between 0 and 1, got {self.target_percentage}"
            )
        if self.team_day is not None and not 0 <= self.team_day <= 6:
            raise ValueError(
                f"Team day must be between 0 (Mon) and 6 (Sun), got {self.team_day}"
            )

    def is_team_day(self, day_of_week: int) -> bool:
        """Check if this day of the week is the team-day."""
        return self.team_day is not None and day_of_week == self.team_day


@dataclass
class ScheduleConfig:
    """Complete configuration for shift scheduling."""

    start_date: date
    duration_weeks: int
    staffing_requirements: Dict[int, int]  # day_of_week -> number of people needed
    teams: List[Team]
    employees: List[Employee]
    penalty_team_deviation: float = 10000
    penalty_consecutive_shifts: float = 50

    @property
    def total_days(self) -> int:
        """Total number of days in the planning period."""
        return self.duration_weeks * 7

    @property
    def team_names(self) -> List[str]:
        """List of all team names."""
        return [team.name for team in self.teams]

    def get_team(self, team_name: str) -> Team:
        """Get a team by name."""
        for team in self.teams:
            if team.name == team_name:
                return team
        raise ValueError(f"Team '{team_name}' not found")

    def employees_in_team(self, team_name: str) -> List[Employee]:
        """Get all employees in a specific team."""
        return [emp for emp in self.employees if emp.team == team_name]


@dataclass
class EmployeeSchedule:
    """Represents the schedule for a single employee."""

    employee: Employee
    assigned_days: List[int]  # Day indices where employee works
    ideal_shifts: float
    actual_shifts: int
    max_consecutive: int
    violations_count: int  # Number of times worked >3 consecutive days

    @property
    def deviation(self) -> float:
        """Deviation from ideal shifts."""
        return self.actual_shifts - self.ideal_shifts


@dataclass
class DailyAssignment:
    """Represents who is working on a specific day."""

    day_index: int
    date: date
    day_of_week: str
    employees: List[str]  # Employee names
    required: int
    actual: int


@dataclass
class TeamSummary:
    """Summary statistics for a team."""

    team: Team
    target_shifts: float
    actual_shifts: float
    deviation: float

    @property
    def actual_percentage(self) -> float:
        """Actual percentage of total shifts covered by this team."""
        return self.actual_shifts / sum(
            self.actual_shifts for _ in [self]
        )  # Will be calculated properly


@dataclass
class ScheduleResult:
    """Complete result of the scheduling optimization."""

    config: ScheduleConfig
    status: str
    objective_value: float
    daily_assignments: List[DailyAssignment]
    employee_schedules: List[EmployeeSchedule]
    team_summaries: List[TeamSummary]
    total_shifts_required: int

    @property
    def is_optimal(self) -> bool:
        """Check if an optimal solution was found."""
        return self.status == "Optimal"

    def get_employee_schedule(self, employee_name: str) -> EmployeeSchedule:
        """Get the schedule for a specific employee."""
        for emp_sched in self.employee_schedules:
            if emp_sched.employee.name == employee_name:
                return emp_sched
        raise ValueError(f"Employee '{employee_name}' not found in results")
