"""
Configuration loader for parsing YAML schedule configuration.
"""

import yaml
from pathlib import Path
from typing import Dict, Any
from datetime import date, timedelta

from .models import ScheduleConfig, Employee, Team, VacationPeriod


class ConfigurationError(Exception):
    """Custom exception for configuration errors."""

    pass


class InvalidDateFormatError(ConfigurationError):
    """Raised when a date is not in ISO 8601 format (YYYY-MM-DD)."""

    pass


class ConfigLoader:
    """Loads and validates shift scheduling configuration from YAML files."""

    # Class-level constants
    DAY_NAME_TO_INDEX = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }

    def __init__(self, config_path: str | Path):
        """
        Initialize the ConfigLoader with a configuration file path.

        Args:
            config_path: Path to the YAML configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
        """
        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        self._raw_config: Dict[str, Any] | None = None
        self._config: ScheduleConfig | None = None

    def load(self) -> ScheduleConfig:
        """
        Load and parse the configuration file.

        Returns:
            ScheduleConfig object with all parsed data

        Raises:
            InvalidDateFormatError: If dates are not in ISO 8601 format
            ConfigurationError: If configuration is invalid
        """
        # Read the YAML file
        with open(self.config_path, "r") as f:
            self._raw_config = yaml.safe_load(f)

        # Parse into structured config
        self._config = self._parse_config()

        # Validate the config
        self._validate()

        return self._config

    def reload(self) -> ScheduleConfig:
        """
        Reload the configuration from the file.

        Useful if the file has been modified.

        Returns:
            ScheduleConfig object with all parsed data
        """
        return self.load()

    @property
    def config(self) -> ScheduleConfig:
        """
        Get the loaded configuration.

        Returns:
            ScheduleConfig object

        Raises:
            RuntimeError: If load() hasn't been called yet
        """
        if self._config is None:
            raise RuntimeError("Configuration not loaded. Call load() first.")
        return self._config

    @property
    def raw_config(self) -> Dict[str, Any]:
        """
        Get the raw configuration dictionary.

        Returns:
            Raw configuration dictionary from YAML

        Raises:
            RuntimeError: If load() hasn't been called yet
        """
        if self._raw_config is None:
            raise RuntimeError("Configuration not loaded. Call load() first.")
        return self._raw_config

    def _parse_config(self) -> ScheduleConfig:
        """Parse raw YAML data into ScheduleConfig object."""
        raw = self._raw_config

        # Parse planning period
        planning = raw.get("planning", {})
        start_date = planning.get("start_date")
        if not isinstance(start_date, date):
            raise InvalidDateFormatError(
                f"start_date must be in ISO 8601 format (YYYY-MM-DD), got: {start_date}. "
                f"Example: 2026-01-01"
            )

        duration_weeks = planning.get("duration_weeks", 4)

        # Parse staffing requirements
        staffing_requirements = self._parse_staffing_requirements(
            raw.get("staffing_requirements", {})
        )

        # Parse teams
        teams = self._parse_teams(raw.get("teams", {}))

        # Parse employees
        employees = self._parse_employees(raw.get("employees", []))

        # Parse penalties
        penalties = raw.get("penalties", {})
        penalty_team = penalties.get("team_deviation", 10000)
        penalty_consecutive = penalties.get("consecutive_shifts", 50)

        return ScheduleConfig(
            start_date=start_date,
            duration_weeks=duration_weeks,
            staffing_requirements=staffing_requirements,
            teams=teams,
            employees=employees,
            penalty_team_deviation=penalty_team,
            penalty_consecutive_shifts=penalty_consecutive,
        )

    def _parse_staffing_requirements(
        self, staffing_raw: Dict[str, int]
    ) -> Dict[int, int]:
        """Parse staffing requirements from day names to day indices."""
        staffing_requirements = {}

        for day_name, count in staffing_raw.items():
            day_index = self.DAY_NAME_TO_INDEX.get(day_name.lower())
            if day_index is None:
                raise ConfigurationError(
                    f"Invalid day name: '{day_name}'. "
                    f"Valid names: {', '.join(self.DAY_NAME_TO_INDEX.keys())}"
                )
            staffing_requirements[day_index] = count

        # Ensure all days are covered (default to 0 if missing)
        for i in range(7):
            if i not in staffing_requirements:
                staffing_requirements[i] = 0

        return staffing_requirements

    def _parse_teams(self, teams_raw: Dict[str, Any]) -> list[Team]:
        """Parse teams from raw config."""
        teams = []
        total_percentage = 0.0

        for team_name, team_data in teams_raw.items():
            target_pct = team_data.get("target_percentage", 0.0)
            team_day = team_data.get("team_day", None)
            teams.append(
                Team(name=team_name, target_percentage=target_pct, team_day=team_day)
            )
            total_percentage += target_pct

        # Validate team percentages sum to ~1.0
        if abs(total_percentage - 1.0) > 0.01:
            raise ConfigurationError(
                f"Team target percentages must sum to 1.0, got {total_percentage:.2f}"
            )

        return teams

    def _parse_employees(self, employees_raw: list[Dict[str, Any]]) -> list[Employee]:
        """Parse employees from raw config."""
        employees = []

        for emp_data in employees_raw:
            name = emp_data.get("name")
            team = emp_data.get("team")
            available_days = emp_data.get("available_days", [])

            # Parse vacations
            vacations = self._parse_vacations(emp_data.get("vacations", []), name)

            employees.append(
                Employee(
                    name=name,
                    team=team,
                    available_days=available_days,
                    vacations=vacations,
                )
            )

        return employees

    def _parse_vacations(
        self, vacations_raw: list[Dict[str, Any]], employee_name: str
    ) -> list[VacationPeriod]:
        """Parse vacation periods for an employee."""
        vacations = []

        for vac_data in vacations_raw:
            start = vac_data.get("start")
            end = vac_data.get("end")

            if not isinstance(start, date):
                raise InvalidDateFormatError(
                    f"Vacation start date for {employee_name} must be in ISO 8601 format "
                    f"(YYYY-MM-DD), got: {start}. Example: 2026-01-15"
                )

            if not isinstance(end, date):
                raise InvalidDateFormatError(
                    f"Vacation end date for {employee_name} must be in ISO 8601 format "
                    f"(YYYY-MM-DD), got: {end}. Example: 2026-01-20"
                )

            vacations.append(VacationPeriod(start=start, end=end))

        return vacations

    def _validate(self) -> None:
        """
        Validate that the configuration is internally consistent.

        Raises:
            ConfigurationError: If configuration has issues
        """
        config = self._config

        # Check that all employees belong to defined teams
        team_names = config.team_names
        for emp in config.employees:
            if emp.team not in team_names:
                raise ConfigurationError(
                    f"Employee '{emp.name}' belongs to undefined team '{emp.team}'. "
                    f"Defined teams: {', '.join(team_names)}"
                )

        # Check that each team has at least one employee
        for team in config.teams:
            if not config.employees_in_team(team.name):
                raise ConfigurationError(
                    f"Team '{team.name}' has no employees assigned to it"
                )

        # Warn if vacations are outside planning period
        self._check_vacation_dates()

    def _check_vacation_dates(self) -> None:
        """Check and warn if vacation dates are outside the planning period."""
        config = self._config
        end_date = config.start_date + timedelta(days=config.total_days - 1)

        for emp in config.employees:
            for vac in emp.vacations:
                if vac.end < config.start_date or vac.start > end_date:
                    print(
                        f"Warning: {emp.name}'s vacation {vac.start} to {vac.end} "
                        f"is outside planning period {config.start_date} to {end_date}"
                    )

    def get_summary(self) -> str:
        """
        Get a summary of the loaded configuration.

        Returns:
            Human-readable summary string

        Raises:
            RuntimeError: If load() hasn't been called yet
        """
        config = self.config

        lines = [
            f"Configuration from: {self.config_path}",
            f"Planning Period: {config.start_date} to "
            f"{config.start_date + timedelta(days=config.total_days - 1)}",
            f"Duration: {config.duration_weeks} weeks ({config.total_days} days)",
            f"Teams: {len(config.teams)}",
        ]

        for team in config.teams:
            emp_count = len(config.employees_in_team(team.name))
            lines.append(
                f"  - {team.name}: {emp_count} employees ({team.target_percentage*100:.0f}%)"
            )

        lines.append(f"Total Employees: {len(config.employees)}")

        return "\n".join(lines)
