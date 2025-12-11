"""
Steward Shift - Employee shift scheduling optimization using linear programming.
"""

__version__ = "0.1.0"

from .config import ConfigLoader, ConfigurationError, InvalidDateFormatError
from .models import (
    DailyAssignment,
    Employee,
    EmployeeSchedule,
    ScheduleConfig,
    ScheduleResult,
    Team,
    TeamSummary,
    VacationPeriod,
)
from .optimizer import ShiftOptimizer
from .reporter import ScheduleReporter

__all__ = [
    "ConfigLoader",
    "ConfigurationError",
    "InvalidDateFormatError",
    "ScheduleConfig",
    "Employee",
    "Team",
    "VacationPeriod",
    "ScheduleResult",
    "EmployeeSchedule",
    "DailyAssignment",
    "TeamSummary",
    "ShiftOptimizer",
    "ScheduleReporter",
]
