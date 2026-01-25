"""Tests for configuration loading and validation."""

import pytest
import tempfile
from pathlib import Path

from steward_shift.config import (
    ConfigLoader,
    ConfigurationError,
    InvalidDateFormatError,
)


def write_yaml(content: str) -> Path:
    """Write YAML content to a temporary file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


class TestConfigLoaderBasics:
    """Basic config loading tests."""

    def test_file_not_found_raises_error(self):
        """Loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ConfigLoader("/nonexistent/path.yaml")

    def test_load_minimal_valid_config(self):
        """Minimal valid YAML config loads successfully."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1
  tuesday: 1
  wednesday: 1
  thursday: 1
  friday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0, 1, 2, 3, 4]
"""
        path = write_yaml(yaml)
        loader = ConfigLoader(path)
        config = loader.load()

        assert config.duration_weeks == 1
        assert len(config.employees) == 1
        assert config.employees[0].name == "Alice"


class TestDateParsing:
    """Tests for date format validation."""

    def test_iso8601_date_accepted(self):
        """ISO 8601 dates (YYYY-MM-DD) are accepted."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.start_date.year == 2026
        assert config.start_date.month == 1
        assert config.start_date.day == 5

    def test_non_iso_date_raises_error(self):
        """Non-ISO date format raises InvalidDateFormatError."""
        yaml = """
planning:
  start_date: "01/05/2026"
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        with pytest.raises(InvalidDateFormatError, match="ISO 8601"):
            ConfigLoader(path).load()


class TestDayNameMapping:
    """Tests for day name to index mapping."""

    @pytest.mark.parametrize(
        "day_name,expected_index",
        [
            ("monday", 0),
            ("tuesday", 1),
            ("wednesday", 2),
            ("thursday", 3),
            ("friday", 4),
            ("saturday", 5),
            ("sunday", 6),
        ],
    )
    def test_day_names_map_correctly(self, day_name: str, expected_index: int):
        """Day names map to correct indices."""
        yaml = f"""
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  {day_name}: 5

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0, 1, 2, 3, 4, 5, 6]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.staffing_requirements[expected_index] == 5

    def test_case_insensitive_day_names(self):
        """Day names are case-insensitive."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  MONDAY: 1
  Tuesday: 2
  wEdNeSdAy: 3

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0, 1, 2]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.staffing_requirements[0] == 1
        assert config.staffing_requirements[1] == 2
        assert config.staffing_requirements[2] == 3

    def test_invalid_day_name_raises_error(self):
        """Invalid day name raises ConfigurationError."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  notaday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        with pytest.raises(ConfigurationError, match="Invalid day name"):
            ConfigLoader(path).load()


class TestTeamValidation:
    """Tests for team configuration validation."""

    def test_team_percentages_must_sum_to_one(self):
        """Team percentages that don't sum to 1.0 raise error."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 0.3
  TeamB:
    target_percentage: 0.3

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
  - name: Bob
    team: TeamB
    available_days: [0]
"""
        path = write_yaml(yaml)
        with pytest.raises(ConfigurationError, match="sum to 1.0"):
            ConfigLoader(path).load()

    def test_team_with_no_employees_raises_error(self):
        """Team with no employees raises ConfigurationError."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 0.5
  TeamB:
    target_percentage: 0.5

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        with pytest.raises(ConfigurationError, match="no employees"):
            ConfigLoader(path).load()

    def test_employee_with_undefined_team_raises_error(self):
        """Employee referencing undefined team raises error."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: NonExistent
    available_days: [0]
"""
        path = write_yaml(yaml)
        with pytest.raises(ConfigurationError, match="undefined team"):
            ConfigLoader(path).load()


class TestConstraintsParsing:
    """Tests for parsing constraints section."""

    def test_default_max_consecutive_shifts(self):
        """Default max_consecutive_shifts is 3 when not specified."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.max_consecutive_shifts == 3

    @pytest.mark.parametrize("max_consec", [1, 2, 3, 5, 10])
    def test_custom_max_consecutive_shifts(self, max_consec: int):
        """max_consecutive_shifts can be set via constraints section."""
        yaml = f"""
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]

constraints:
  max_consecutive_shifts: {max_consec}
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.max_consecutive_shifts == max_consec

    def test_default_max_shifts_per_week(self):
        """Default max_shifts_per_week is 1 when not specified."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.max_shifts_per_week == 1

    @pytest.mark.parametrize("max_weekly", [1, 2, 3, 5])
    def test_custom_max_shifts_per_week(self, max_weekly: int):
        """max_shifts_per_week can be set via constraints section."""
        yaml = f"""
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]

constraints:
  max_shifts_per_week: {max_weekly}
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.max_shifts_per_week == max_weekly

    def test_default_penalty_weekly_shifts(self):
        """Default penalty_weekly_shifts is 30 when not specified."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.penalty_weekly_shifts == 30

    def test_custom_penalty_weekly_shifts(self):
        """penalty_weekly_shifts can be set via penalties section."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]

penalties:
  weekly_shifts: 100
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.penalty_weekly_shifts == 100

    def test_default_prevent_same_day_consecutive_weeks(self):
        """Default prevent_same_day_consecutive_weeks is True."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.prevent_same_day_consecutive_weeks is True

    def test_prevent_same_day_can_be_disabled(self):
        """prevent_same_day_consecutive_weeks can be set to false."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]

constraints:
  prevent_same_day_consecutive_weeks: false
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.prevent_same_day_consecutive_weeks is False

    def test_default_penalty_same_day_consecutive_weeks(self):
        """Default penalty_same_day_consecutive_weeks is 10."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.penalty_same_day_consecutive_weeks == 10

    def test_custom_penalty_same_day_consecutive_weeks(self):
        """penalty_same_day_consecutive_weeks can be customized."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]

penalties:
  same_day_consecutive_weeks: 50
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert config.penalty_same_day_consecutive_weeks == 50


class TestVacationParsing:
    """Tests for vacation period parsing."""

    def test_vacation_dates_parsed_correctly(self):
        """Vacation start and end dates are parsed."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 2

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0, 1, 2, 3, 4]
    vacations:
      - start: 2026-01-07
        end: 2026-01-09
"""
        path = write_yaml(yaml)
        config = ConfigLoader(path).load()
        assert len(config.employees[0].vacations) == 1
        vac = config.employees[0].vacations[0]
        assert vac.start.day == 7
        assert vac.end.day == 9

    def test_invalid_vacation_date_raises_error(self):
        """Invalid vacation date format raises error."""
        yaml = """
planning:
  start_date: 2026-01-05
  duration_weeks: 1

staffing_requirements:
  monday: 1

teams:
  TeamA:
    target_percentage: 1.0

employees:
  - name: Alice
    team: TeamA
    available_days: [0]
    vacations:
      - start: "Jan 7, 2026"
        end: 2026-01-09
"""
        path = write_yaml(yaml)
        with pytest.raises(InvalidDateFormatError):
            ConfigLoader(path).load()
