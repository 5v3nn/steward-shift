"""
Export strategies for schedule data.

This module implements the Strategy Pattern for exporting schedule results
to various formats. Each exporter encapsulates a specific output format.
"""

import csv
from abc import ABC, abstractmethod
from datetime import date, timedelta

from .models import ScheduleResult, EmployeeSchedule


class ExportStrategy(ABC):
    """Abstract base class for schedule export strategies.

    Subclasses implement specific export formats (CSV, Excel, etc.).
    Common helper methods for data transformation are provided here.
    """

    def __init__(self, result: ScheduleResult):
        """Initialize the export strategy.

        Args:
            result: The schedule result to export
        """
        self.result = result

    @abstractmethod
    def export(self, filepath: str) -> None:
        """Export schedule to the specified file.

        Args:
            filepath: Path to the output file
        """
        pass

    def _get_date_range(self) -> list[date]:
        """Get ordered list of all dates in the scheduling period.

        Returns:
            List of dates from start to end of planning period
        """
        return [
            self.result.config.start_date + timedelta(days=k)
            for k in range(self.result.config.total_days)
        ]

    def _build_employee_assignment_map(self) -> dict[str, set[date]]:
        """Build lookup map from employee name to set of assigned dates.

        Returns:
            Dictionary mapping employee names to their assigned dates
        """
        assignment_map: dict[str, set[date]] = {}
        for emp_sched in self.result.employee_schedules:
            assigned_dates = {
                self.result.config.start_date + timedelta(days=day_idx)
                for day_idx in emp_sched.assigned_days
            }
            assignment_map[emp_sched.employee.name] = assigned_dates
        return assignment_map

    def _group_employees_by_team(self) -> dict[str, list[EmployeeSchedule]]:
        """Group employee schedules by team, maintaining config order.

        Returns:
            Dictionary mapping team name to list of EmployeeSchedule objects,
            ordered by team definition order from config, employees sorted
            alphabetically within each team
        """
        grouped: dict[str, list[EmployeeSchedule]] = {}

        # Initialize with team order from config
        for team in self.result.config.teams:
            grouped[team.name] = []

        # Populate with employees
        for emp_sched in self.result.employee_schedules:
            team_name = emp_sched.employee.team
            if team_name in grouped:
                grouped[team_name].append(emp_sched)

        # Sort employees within each team by name
        for team_name in grouped:
            grouped[team_name].sort(key=lambda es: es.employee.name)

        return grouped


class SimpleCSVExporter(ExportStrategy):
    """Exports schedule as simple 3-column CSV.

    Output format: Date, Day_of_Week, Employee
    One row per employee assignment per day.
    """

    def export(self, filepath: str) -> None:
        """Export schedule to CSV file in simple format.

        Args:
            filepath: Path to the output CSV file
        """
        rows: list[dict[str, str]] = []

        for assignment in self.result.daily_assignments:
            for emp_name in assignment.employees:
                rows.append(
                    {
                        "Date": assignment.date.isoformat(),
                        "Day_of_Week": assignment.day_of_week,
                        "Employee": emp_name,
                    }
                )

        with open(filepath, "w", newline="") as f:
            if rows:
                writer = csv.DictWriter(
                    f, fieldnames=["Date", "Day_of_Week", "Employee"]
                )
                writer.writeheader()
                writer.writerows(rows)
            else:
                writer = csv.writer(f)
                writer.writerow(["Date", "Day_of_Week", "Employee"])

        print(f"\n✓ Schedule exported to {filepath}")


class MatrixCSVExporter(ExportStrategy):
    """Exports schedule as matrix with team groupings and formulas.

    Output format:
    - First column: Employee name (or team header)
    - Subsequent columns: One per date
    - Employees grouped by team with team header rows
    - Sum formulas at bottom for each date column
    """

    def __init__(self, result: ScheduleResult, shift_marker: str = "X"):
        """Initialize the matrix CSV exporter.

        Args:
            result: The schedule result to export
            shift_marker: Character to mark shift assignments (default: "X")
        """
        super().__init__(result)
        self.shift_marker = shift_marker

    def export(self, filepath: str) -> None:
        """Export schedule to CSV file in matrix format.

        Args:
            filepath: Path to the output CSV file
        """
        dates = self._get_date_range()
        assignment_map = self._build_employee_assignment_map()
        teams_grouped = self._group_employees_by_team()

        rows: list[list[str]] = []
        employee_row_indices: list[int] = []

        # Header row
        header = self._build_header_row(dates)
        rows.append(header)

        # Track current row (1-indexed for Excel, row 1 is header)
        current_row = 2

        # Team sections
        for team_name, emp_schedules in teams_grouped.items():
            # Team header row
            team_header = [f"--- {team_name} ---"] + [""] * len(dates)
            rows.append(team_header)
            current_row += 1

            # Employee rows
            for emp_sched in emp_schedules:
                emp_dates = assignment_map.get(emp_sched.employee.name, set())
                row = [emp_sched.employee.name]
                for d in dates:
                    row.append(self.shift_marker if d in emp_dates else "")
                rows.append(row)
                employee_row_indices.append(current_row)
                current_row += 1

        # Sum row with formulas
        total_row = self._build_total_row(len(dates), current_row)
        rows.append(total_row)

        # Write to CSV
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        print(f"\n✓ Schedule exported to {filepath} (matrix format)")

    def _build_header_row(self, dates: list[date]) -> list[str]:
        """Build the header row with Employee column and date columns.

        Args:
            dates: List of dates for column headers

        Returns:
            List of header strings
        """
        header = ["Employee"]
        for d in dates:
            header.append(f"{d.strftime('%Y-%m-%d')} {d.strftime('%a')}")
        return header

    def _build_total_row(self, num_date_cols: int, next_row: int) -> list[str]:
        """Build the TOTAL row with COUNTIF formulas.

        Args:
            num_date_cols: Number of date columns
            next_row: The row number after the last data row (1-indexed)

        Returns:
            List with "TOTAL" and COUNTIF formulas for each column
        """
        total_row = ["TOTAL"]
        last_data_row = next_row - 1

        for col_idx in range(num_date_cols):
            col_letter = self._col_index_to_excel_letter(col_idx + 1)
            formula = f'=COUNTIF({col_letter}2:{col_letter}{last_data_row},"{self.shift_marker}")'
            total_row.append(formula)

        return total_row

    def _col_index_to_excel_letter(self, index: int) -> str:
        """Convert 0-based column index to Excel column letter.

        Args:
            index: 0-based column index

        Returns:
            Excel column letter (A, B, ..., Z, AA, AB, ...)
        """
        result = ""
        index += 1  # Convert to 1-based
        while index > 0:
            index -= 1
            result = chr(index % 26 + ord("A")) + result
            index //= 26
        return result
