"""Tests for schedule export strategies."""

import csv
import pytest
from datetime import date

from steward_shift.models import (
    Employee,
    Team,
    ScheduleConfig,
    ScheduleResult,
)
from steward_shift.exporters import (
    ExportStrategy,
    SimpleCSVExporter,
    MatrixCSVExporter,
)
from steward_shift.optimizer import ShiftOptimizer


@pytest.fixture
def simple_result(minimal_config: ScheduleConfig) -> ScheduleResult:
    """Generate a simple schedule result for testing."""
    optimizer = ShiftOptimizer(minimal_config)
    return optimizer.optimize()


@pytest.fixture
def multi_team_config() -> ScheduleConfig:
    """Config with multiple teams for testing team grouping."""
    return ScheduleConfig(
        start_date=date(2026, 1, 5),  # Monday
        duration_weeks=1,
        staffing_requirements={
            0: 2,  # Mon
            1: 2,  # Tue
            2: 2,  # Wed
            3: 2,  # Thu
            4: 2,  # Fri
            5: 0,  # Sat
            6: 0,  # Sun
        },
        teams=[
            Team(name="Alpha", target_percentage=0.5),
            Team(name="Beta", target_percentage=0.3),
            Team(name="Gamma", target_percentage=0.2),
        ],
        employees=[
            Employee(name="Alice", team="Alpha", available_days=[0, 1, 2, 3, 4]),
            Employee(name="Bob", team="Alpha", available_days=[0, 1, 2, 3, 4]),
            Employee(name="Carol", team="Beta", available_days=[0, 1, 2, 3, 4]),
            Employee(name="Dan", team="Beta", available_days=[0, 1, 2, 3, 4]),
            Employee(name="Eve", team="Gamma", available_days=[0, 1, 2, 3, 4]),
        ],
    )


@pytest.fixture
def multi_team_result(multi_team_config: ScheduleConfig) -> ScheduleResult:
    """Generate a multi-team schedule result for testing."""
    optimizer = ShiftOptimizer(multi_team_config)
    return optimizer.optimize()


class TestExportStrategyBase:
    """Tests for the ExportStrategy abstract base class."""

    def test_cannot_instantiate_abstract_class(self, simple_result: ScheduleResult):
        """ExportStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ExportStrategy(simple_result)

    def test_get_date_range(self, simple_result: ScheduleResult):
        """_get_date_range returns correct dates."""
        exporter = SimpleCSVExporter(simple_result)
        dates = exporter._get_date_range()

        assert len(dates) == simple_result.config.total_days
        assert dates[0] == simple_result.config.start_date
        assert dates[-1] == date(2026, 1, 11)  # 7 days from Jan 5

    def test_build_employee_assignment_map(self, simple_result: ScheduleResult):
        """_build_employee_assignment_map returns correct mapping."""
        exporter = SimpleCSVExporter(simple_result)
        assignment_map = exporter._build_employee_assignment_map()

        # Verify all employees are in the map
        for emp_sched in simple_result.employee_schedules:
            assert emp_sched.employee.name in assignment_map

        # Verify dates are correct for at least one employee
        for emp_sched in simple_result.employee_schedules:
            emp_dates = assignment_map[emp_sched.employee.name]
            expected_dates = {
                simple_result.config.start_date
                + __import__("datetime").timedelta(days=d)
                for d in emp_sched.assigned_days
            }
            assert emp_dates == expected_dates

    def test_group_employees_by_team(self, multi_team_result: ScheduleResult):
        """_group_employees_by_team groups correctly and maintains order."""
        exporter = SimpleCSVExporter(multi_team_result)
        grouped = exporter._group_employees_by_team()

        # Check team order matches config order
        team_names = list(grouped.keys())
        assert team_names == ["Alpha", "Beta", "Gamma"]

        # Check employees are in correct teams
        alpha_names = [es.employee.name for es in grouped["Alpha"]]
        assert set(alpha_names) == {"Alice", "Bob"}

        beta_names = [es.employee.name for es in grouped["Beta"]]
        assert set(beta_names) == {"Carol", "Dan"}

        gamma_names = [es.employee.name for es in grouped["Gamma"]]
        assert set(gamma_names) == {"Eve"}

    def test_employees_sorted_alphabetically_within_team(
        self, multi_team_result: ScheduleResult
    ):
        """Employees are sorted alphabetically within each team."""
        exporter = SimpleCSVExporter(multi_team_result)
        grouped = exporter._group_employees_by_team()

        for team_name, emp_schedules in grouped.items():
            names = [es.employee.name for es in emp_schedules]
            assert names == sorted(names), f"Team {team_name} not sorted"


class TestSimpleCSVExporter:
    """Tests for SimpleCSVExporter."""

    def test_export_creates_file(self, simple_result: ScheduleResult, tmp_path):
        """Export creates a CSV file at the specified path."""
        filepath = tmp_path / "schedule.csv"
        exporter = SimpleCSVExporter(simple_result)
        exporter.export(str(filepath))

        assert filepath.exists()

    def test_export_has_correct_headers(self, simple_result: ScheduleResult, tmp_path):
        """Exported CSV has correct column headers."""
        filepath = tmp_path / "schedule.csv"
        exporter = SimpleCSVExporter(simple_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            headers = next(reader)

        assert headers == ["Date", "Day_of_Week", "Employee"]

    def test_export_has_correct_row_count(
        self, simple_result: ScheduleResult, tmp_path
    ):
        """Exported CSV has one row per assignment plus header."""
        filepath = tmp_path / "schedule.csv"
        exporter = SimpleCSVExporter(simple_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Count total assignments
        total_assignments = sum(
            len(a.employees) for a in simple_result.daily_assignments
        )

        # Rows = header + assignments
        assert len(rows) == 1 + total_assignments

    def test_export_empty_schedule(self, tmp_path):
        """Export handles schedule with no assignments."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=1,
            staffing_requirements={0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[Employee(name="E", team="T", available_days=[0, 1, 2, 3, 4])],
        )
        result = ShiftOptimizer(config).optimize()

        filepath = tmp_path / "empty.csv"
        exporter = SimpleCSVExporter(result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Only header row
        assert len(rows) == 1
        assert rows[0] == ["Date", "Day_of_Week", "Employee"]


class TestMatrixCSVExporter:
    """Tests for MatrixCSVExporter."""

    def test_export_creates_file(self, simple_result: ScheduleResult, tmp_path):
        """Export creates a CSV file at the specified path."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(simple_result)
        exporter.export(str(filepath))

        assert filepath.exists()

    def test_header_row_structure(self, simple_result: ScheduleResult, tmp_path):
        """First row has Employee column and date columns."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(simple_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header[0] == "Employee"
        # Check date format: YYYY-MM-DD Day
        assert "2026-01-05 Mon" in header[1]

    def test_total_row_present(self, simple_result: ScheduleResult, tmp_path):
        """Last row is the TOTAL row with formulas."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(simple_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        last_row = rows[-1]
        assert last_row[0] == "TOTAL"
        # Check formulas are present
        assert last_row[1].startswith("=COUNTIF(")

    def test_team_headers_present(self, multi_team_result: ScheduleResult, tmp_path):
        """Team header rows are present for each team."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(multi_team_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        team_headers = [row[0] for row in rows if row[0].startswith("---")]
        assert "--- Alpha ---" in team_headers
        assert "--- Beta ---" in team_headers
        assert "--- Gamma ---" in team_headers

    def test_team_order_matches_config(
        self, multi_team_result: ScheduleResult, tmp_path
    ):
        """Teams appear in the order specified in config."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(multi_team_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        team_headers = [row[0] for row in rows if row[0].startswith("---")]
        assert team_headers == ["--- Alpha ---", "--- Beta ---", "--- Gamma ---"]

    def test_shift_markers_correct(self, simple_result: ScheduleResult, tmp_path):
        """Shift markers appear in correct cells."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(simple_result, shift_marker="X")
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Find employee rows (not header, team headers, or TOTAL)
        employee_rows = [
            row
            for row in rows
            if row[0] not in ["Employee", "TOTAL"] and not row[0].startswith("---")
        ]

        # Count X markers
        x_count = sum(1 for row in employee_rows for cell in row[1:] if cell == "X")

        # Should match total assignments
        total_assignments = sum(
            len(a.employees) for a in simple_result.daily_assignments
        )
        assert x_count == total_assignments

    def test_custom_shift_marker(self, simple_result: ScheduleResult, tmp_path):
        """Custom shift marker is used instead of X."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(simple_result, shift_marker="1")
        exporter.export(str(filepath))

        with open(filepath) as f:
            content = f.read()

        assert "1" in content
        # Formula should use the custom marker
        assert "=COUNTIF(" in content and '"1"' in content

    def test_col_index_to_excel_letter_single(self, simple_result: ScheduleResult):
        """Column indices 0-25 map to A-Z."""
        exporter = MatrixCSVExporter(simple_result)

        assert exporter._col_index_to_excel_letter(0) == "A"
        assert exporter._col_index_to_excel_letter(1) == "B"
        assert exporter._col_index_to_excel_letter(25) == "Z"

    def test_col_index_to_excel_letter_double(self, simple_result: ScheduleResult):
        """Column indices 26+ map to AA, AB, etc."""
        exporter = MatrixCSVExporter(simple_result)

        assert exporter._col_index_to_excel_letter(26) == "AA"
        assert exporter._col_index_to_excel_letter(27) == "AB"
        assert exporter._col_index_to_excel_letter(51) == "AZ"
        assert exporter._col_index_to_excel_letter(52) == "BA"

    def test_formula_references_correct_range(
        self, simple_result: ScheduleResult, tmp_path
    ):
        """COUNTIF formulas reference correct row range."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(simple_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        total_row = rows[-1]
        # First formula is in column B (index 1)
        first_formula = total_row[1]

        # Formula should start from row 2 (after header)
        assert ":B2" in first_formula or "B2:" in first_formula

    def test_employees_sorted_within_teams(
        self, multi_team_result: ScheduleResult, tmp_path
    ):
        """Employees are sorted alphabetically within each team section."""
        filepath = tmp_path / "matrix.csv"
        exporter = MatrixCSVExporter(multi_team_result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Extract employee names between team headers
        current_team_employees = []
        for row in rows:
            if row[0].startswith("---"):
                if current_team_employees:
                    assert current_team_employees == sorted(current_team_employees)
                current_team_employees = []
            elif row[0] not in ["Employee", "TOTAL"]:
                current_team_employees.append(row[0])

    def test_long_schedule_column_letters(self, tmp_path):
        """Schedules longer than 26 days use AA, AB, etc. columns."""
        config = ScheduleConfig(
            start_date=date(2026, 1, 5),
            duration_weeks=5,  # 35 days, needs columns past Z
            staffing_requirements={0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 0},
            teams=[Team(name="T", target_percentage=1.0)],
            employees=[
                Employee(name="E1", team="T", available_days=[0, 1, 2, 3, 4]),
                Employee(name="E2", team="T", available_days=[0, 1, 2, 3, 4]),
            ],
        )
        result = ShiftOptimizer(config).optimize()

        filepath = tmp_path / "long.csv"
        exporter = MatrixCSVExporter(result)
        exporter.export(str(filepath))

        with open(filepath) as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Check that formulas for later columns use AA, AB, etc.
        total_row = rows[-1]
        # Column 27 (index 26) should be AA
        # But we have 35 days, so we should have formulas up to around AI
        assert len(total_row) > 27  # More than just A-Z columns
