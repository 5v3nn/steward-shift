"""
Reporting and output formatting for shift schedules.
"""

import pandas as pd
from typing import List, Tuple
from datetime import timedelta

from .models import ScheduleResult


class ScheduleReporter:
    """Formats and displays scheduling results."""

    def __init__(self, result: ScheduleResult):
        self.result = result

    def print_report(self, quiet: bool) -> None:
        """Print complete scheduling report."""
        self._print_header()

        if not self.result.is_optimal:
            self._print_failure_message()
            return

        self._print_daily_schedule()

        if not quiet:
            self._print_employee_summary()
            self._print_team_summary()
            self._print_availability_summary()
            self._print_vacation_summary()
            self._print_consecutive_violations()
            self._print_weekly_violations()
            self._print_same_day_consecutive_weeks_violations()

    def _print_title(self, title: str) -> None:
        print("=" * 80)
        print(title)
        print("=" * 80)

    def _print_header(self) -> None:
        """Print report header."""
        self._print_title("SHIFT SCHEDULE OPTIMIZATION RESULTS")

        print(f"\nStatus: {self.result.status}")
        print(f"Objective Value: {self.result.objective_value:.2f}")
        print(
            f"Planning Period: {self.result.config.start_date} to "
            f"{self.result.config.start_date + timedelta(days=self.result.config.total_days - 1)}"
        )
        print(f"Total Shifts Required: {self.result.total_shifts_required}")
        print()

    def _print_failure_message(self) -> None:
        """Print message when optimization fails."""
        print("\nNO OPTIMAL SOLUTION FOUND!")
        print("\nPossible reasons:")
        print("  • Part-time availability conflicts with staffing requirements")
        print("  • Team distribution targets are impossible with current constraints")
        print("  • Too many vacation conflicts")
        print("\nSuggestions:")
        print("  • Review vacation schedules for conflicts")
        print("  • Check if part-time employees have sufficient availability")
        print("  • Consider adjusting team target percentages")
        print("  • Verify staffing requirements are realistic")

    def _print_daily_schedule(self) -> None:
        """Print day-by-day schedule."""
        self._print_title("DAILY SCHEDULE")

        for assignment in self.result.daily_assignments:
            employees_str = (
                ", ".join(assignment.employees) if assignment.employees else ""
            )
            req_str = f"[Required: {assignment.required}]"

            print(
                f"Day {assignment.day_index + 1:2d} "
                f"({assignment.date.strftime('%Y-%m-%d')} {assignment.day_of_week}): "
                f"{employees_str:40s} {req_str}"
            )

    def _print_employee_summary(self) -> None:
        """Print employee shift summary table."""
        self._print_title("EMPLOYEE SUMMARY")

        data = []
        for emp_sched in self.result.employee_schedules:
            available_days = sum(
                1
                for k in range(self.result.config.total_days)
                if emp_sched.employee.is_available_on_date(
                    self.result.config.start_date + timedelta(days=k),
                    (self.result.config.start_date.weekday() + k) % 7,
                )
            )

            max_consec = self.result.config.max_consecutive_shifts
            max_weekly = self.result.config.max_shifts_per_week

            data.append(
                {
                    "Employee": emp_sched.employee.name,
                    "Team": emp_sched.employee.team,
                    "Available Days": available_days,
                    "Ideal Shifts": emp_sched.ideal_shifts,
                    "Actual Shifts": emp_sched.actual_shifts,
                    "Deviation": emp_sched.deviation,
                    "Max Consecutive": emp_sched.max_consecutive,
                    f"Consec Viol (>{max_consec})": emp_sched.consecutive_violations,
                    "Max Weekly": emp_sched.max_weekly_shifts,
                    f"Weekly Viol (>{max_weekly})": emp_sched.weekly_violations,
                    "Same Day Viol": emp_sched.same_day_consecutive_weeks_violations,
                }
            )

        df = pd.DataFrame(data)
        df = df.set_index("Employee")

        # Format the display
        pd.options.display.float_format = "{:.2f}".format
        print(df.to_string())
        print()

    def _print_team_summary(self) -> None:
        """Print team distribution summary."""
        self._print_title("TEAM SUMMARY")

        data = []
        for team_sum in self.result.team_summaries:
            actual_pct = team_sum.actual_shifts / self.result.total_shifts_required

            data.append(
                {
                    "Team": team_sum.team.name,
                    "Target %": team_sum.team.target_percentage * 100,
                    "Actual %": actual_pct * 100,
                    "Target Shifts": team_sum.target_shifts,
                    "Actual Shifts": team_sum.actual_shifts,
                    "Deviation": team_sum.deviation,
                }
            )

        df = pd.DataFrame(data).set_index("Team")
        pd.options.display.float_format = "{:.2f}".format
        print(df.to_string())
        print()

    def _print_availability_summary(self) -> None:
        """Print employee availability patterns."""
        self._print_title("AVAILABILITY PATTERNS")

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # Group by team
        teams = {}
        for emp_sched in self.result.employee_schedules:
            team_name = emp_sched.employee.team
            if team_name not in teams:
                teams[team_name] = []
            teams[team_name].append(emp_sched)

        for team_name, emp_schedules in teams.items():
            team = self.result.config.get_team(team_name)
            print(f"\n  Team {team_name}:")

            # Show team day if exists
            if team.team_day is not None:
                team_day_name = day_names[team.team_day]
                print(
                    f"    Team Day: {team_day_name} (no {team_name} staff work on {team_day_name}s)"
                )

            # Show each employee
            for emp_sched in emp_schedules:
                emp = emp_sched.employee
                available_day_names = [day_names[i] for i in emp.available_days]

                status = "Full-time" if len(emp.available_days) == 7 else "Part-time"

                print(
                    f"    {emp.name:10s} ({status:10s}): {', '.join(available_day_names)}"
                )

    def _print_vacation_summary(self) -> None:
        """Print vacation schedules."""
        self._print_title("VACATION SCHEDULE")

        has_vacations = False

        for emp_sched in self.result.employee_schedules:
            emp = emp_sched.employee
            if emp.vacations:
                has_vacations = True
                print(f"\n  {emp.name}:")
                for vac in emp.vacations:
                    if vac.start == vac.end:
                        print(f"    • {vac.start.strftime('%Y-%m-%d (%a)')}")
                    else:
                        print(
                            f"    • {vac.start.strftime('%Y-%m-%d (%a)')} to "
                            f"{vac.end.strftime('%Y-%m-%d (%a)')} ({vac.duration_days} days)"
                        )

        if not has_vacations:
            print("\n  No vacations scheduled for this period")

        print()

    def _print_consecutive_violations(self) -> None:
        """Print consecutive shift violations."""
        self._print_title("CONSECUTIVE SHIFT VIOLATIONS")

        violations = self._find_consecutive_violations()

        if not violations:
            print("\n✓ No consecutive shift violations")
            print()
            return

        for emp_name, violation_list in violations:
            print(f"\n  {emp_name}:")
            for start_day, end_day, count in violation_list:
                start_date = self.result.config.start_date + timedelta(days=start_day)
                end_date = self.result.config.start_date + timedelta(days=end_day)
                print(
                    f"    {count} consecutive shifts: "
                    f"Day {start_day + 1} ({start_date.strftime('%a')}) to "
                    f"Day {end_day + 1} ({end_date.strftime('%a')})"
                )
        print()

    def _find_consecutive_violations(
        self,
    ) -> List[Tuple[str, List[Tuple[int, int, int]]]]:
        """
        Find all consecutive shift violations.

        Returns:
            List of (employee_name, [(start_day, end_day, count), ...])
        """
        violations = []

        max_allowed = self.result.config.max_consecutive_shifts

        for emp_sched in self.result.employee_schedules:
            emp_violations = []
            consecutive_count = 0
            start_day = None

            for k in range(self.result.config.total_days):
                if k in emp_sched.assigned_days:
                    if consecutive_count == 0:
                        start_day = k
                    consecutive_count += 1
                else:
                    if consecutive_count > max_allowed:
                        emp_violations.append((start_day, k - 1, consecutive_count))
                    consecutive_count = 0

            # Check if violation extends to end of period
            if consecutive_count > max_allowed:
                emp_violations.append(
                    (start_day, self.result.config.total_days - 1, consecutive_count)
                )

            if emp_violations:
                violations.append((emp_sched.employee.name, emp_violations))

        return violations

    def _print_weekly_violations(self) -> None:
        """Print weekly shift violations."""
        self._print_title("WEEKLY SHIFT VIOLATIONS")

        max_allowed = self.result.config.max_shifts_per_week
        has_violations = False

        for emp_sched in self.result.employee_schedules:
            weeks_with_violations = [
                (week_idx, shifts)
                for week_idx, shifts in enumerate(emp_sched.weekly_shifts)
                if shifts > max_allowed
            ]

            if weeks_with_violations:
                has_violations = True
                print(f"\n  {emp_sched.employee.name}:")
                for week_idx, shifts in weeks_with_violations:
                    week_start = self.result.config.start_date + timedelta(
                        days=week_idx * 7
                    )
                    print(
                        f"    Week {week_idx + 1} ({week_start.strftime('%Y-%m-%d')}): "
                        f"{shifts} shifts (max: {max_allowed})"
                    )

        if not has_violations:
            print(f"\n✓ No weekly shift violations (max {max_allowed} per week)")

        print()

    def _print_same_day_consecutive_weeks_violations(self) -> None:
        """Print same day consecutive weeks violations."""
        if not self.result.config.prevent_same_day_consecutive_weeks:
            return

        self._print_title("SAME DAY CONSECUTIVE WEEKS VIOLATIONS")

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        has_violations = False

        for emp_sched in self.result.employee_schedules:
            if emp_sched.same_day_consecutive_weeks_violations == 0:
                continue

            has_violations = True
            print(f"\n  {emp_sched.employee.name}:")

            # Find specific violations
            assigned_set = set(emp_sched.assigned_days)
            num_weeks = self.result.config.duration_weeks
            start_weekday = self.result.config.start_date.weekday()

            for week_idx in range(num_weeks - 1):
                for day_offset in range(7):
                    day_w = week_idx * 7 + day_offset
                    day_w_plus_1 = (week_idx + 1) * 7 + day_offset

                    if day_w in assigned_set and day_w_plus_1 in assigned_set:
                        date_w = self.result.config.start_date + timedelta(days=day_w)
                        date_w_plus_1 = self.result.config.start_date + timedelta(
                            days=day_w_plus_1
                        )
                        # Convert offset to actual weekday
                        actual_weekday = (start_weekday + day_offset) % 7
                        print(
                            f"    {day_names[actual_weekday]}: "
                            f"Week {week_idx + 1} ({date_w.strftime('%Y-%m-%d')}) and "
                            f"Week {week_idx + 2} ({date_w_plus_1.strftime('%Y-%m-%d')})"
                        )

        if not has_violations:
            print("\n✓ No same day consecutive weeks violations")

        print()

    def export_to_csv(self, filepath: str) -> None:
        """Export schedule to CSV file."""
        data = []

        for assignment in self.result.daily_assignments:
            for emp_name in assignment.employees:
                data.append(
                    {
                        "Date": assignment.date,
                        "Day_of_Week": assignment.day_of_week,
                        "Employee": emp_name,
                    }
                )

        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        print(f"\n✓ Schedule exported to {filepath}")
