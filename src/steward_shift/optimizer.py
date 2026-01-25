"""
Shift scheduling optimization using PuLP linear programming.
"""

import pulp as pl
from datetime import timedelta
from typing import Dict, List

from .models import (
    ScheduleConfig,
    ScheduleResult,
    EmployeeSchedule,
    DailyAssignment,
    TeamSummary,
)


class ShiftOptimizer:
    """Optimizes shift assignments using linear programming."""

    def __init__(self, config: ScheduleConfig):
        self.config = config
        self.prob = None
        self.x = None  # Decision variables
        self.S = None  # Shift count variables
        self.S_t = None  # Team shift count variables
        self.D_t = None  # Team deviation variables
        self.C = None  # Consecutive shift violation variables
        self.W = None  # Weekly shift excess variables
        self.R = None  # Same day consecutive weeks violation variables

    def optimize(self) -> ScheduleResult:
        """
        Run the optimization and return results.

        Returns:
            ScheduleResult object with the optimal schedule
        """
        self._build_problem()
        self._solve()
        return self._extract_results()

    def _build_problem(self) -> None:
        """Build the linear programming problem."""
        cfg = self.config

        # Create index ranges
        D = range(cfg.total_days)
        E = [emp.name for emp in cfg.employees]
        T = cfg.team_names

        # Calculate total shifts required
        self.total_shifts_required = sum(
            cfg.staffing_requirements[(cfg.start_date.weekday() + k) % 7] for k in D
        )

        # Calculate availability matrix A[i][k]
        self.A = self._calculate_availability_matrix(D, E)

        # Calculate available days per employee (for ideal shift calculation)
        self.available_days = {
            emp_name: sum(self.A[emp_name][k] for k in D) for emp_name in E
        }

        # Calculate ideal shifts per employee
        self.ideal_shifts = self._calculate_ideal_shifts(E, T)

        # Create the problem
        self.prob = pl.LpProblem("Employee_Shift_Scheduling", pl.LpMinimize)

        # Decision variables
        self.x = pl.LpVariable.dicts("x", (E, D), 0, 1, pl.LpBinary)
        self.S = pl.LpVariable.dicts(
            "S", E, 0, self.total_shifts_required, pl.LpInteger
        )
        self.S_t = pl.LpVariable.dicts(
            "S_t", T, 0, self.total_shifts_required, pl.LpContinuous
        )
        self.D_t = pl.LpVariable.dicts(
            "D_t", T, 0, self.total_shifts_required, pl.LpContinuous
        )
        self.C = pl.LpVariable.dicts("C", (E, D), 0, 1, pl.LpBinary)

        # Weekly shift excess variables: W[employee][week] = excess shifts above max
        weeks = range(cfg.duration_weeks)
        self.W = pl.LpVariable.dicts("W", (E, weeks), 0, 7, pl.LpInteger)

        # Same day consecutive weeks variables: R[employee][week][day_of_week]
        # Only needed if constraint is enabled and we have at least 2 weeks
        days_of_week = range(7)
        weeks_for_same_day = range(cfg.duration_weeks - 1)  # Pairs: (0,1), (1,2), ...
        if cfg.prevent_same_day_consecutive_weeks and cfg.duration_weeks >= 2:
            self.R = pl.LpVariable.dicts(
                "R", (E, weeks_for_same_day, days_of_week), 0, 1, pl.LpBinary
            )

        # Objective function: minimize fairness deviation + penalties
        fairness_terms = self._add_fairness_objective(E)

        objective = (
            pl.lpSum(fairness_terms)
            + cfg.penalty_team_deviation * pl.lpSum(self.D_t)
            + cfg.penalty_consecutive_shifts
            * pl.lpSum(self.C[i][k] for i in E for k in D)
            + cfg.penalty_weekly_shifts
            * pl.lpSum(self.W[i][w] for i in E for w in weeks)
        )

        # Add same-day penalty only if enabled
        if cfg.prevent_same_day_consecutive_weeks and self.R is not None:
            objective += cfg.penalty_same_day_consecutive_weeks * pl.lpSum(
                self.R[i][w][d]
                for i in E
                for w in weeks_for_same_day
                for d in days_of_week
            )

        self.prob += objective, "Total Cost"

        # Add constraints
        self._add_staffing_constraints(D, E)
        self._add_availability_constraints(D, E)
        self._add_shift_counting_constraints(D, E, T)
        self._add_team_distribution_constraints(T)
        self._add_consecutive_shift_constraints(E, D)
        self._add_weekly_shift_constraints(E, weeks)
        if cfg.prevent_same_day_consecutive_weeks and self.R is not None:
            self._add_same_day_consecutive_weeks_constraints(E, weeks_for_same_day)

    def _calculate_availability_matrix(self, D, E) -> Dict[str, Dict[int, int]]:
        """Calculate A[employee][day] = 1 if available, 0 otherwise."""
        cfg = self.config
        A = {}

        for emp in cfg.employees:
            A[emp.name] = {}
            team = cfg.get_team(emp.team)

            for k in D:
                day_date = cfg.start_date + timedelta(days=k)
                day_of_week = (cfg.start_date.weekday() + k) % 7

                # Check if it's the team-day
                is_team_day = team.is_team_day(day_of_week)

                # Employee is available if:
                # 1. Not the team day
                # 2. Employee works this day of week
                # 3. Employee is not on vacation
                if is_team_day:
                    A[emp.name][k] = 0
                else:
                    A[emp.name][k] = (
                        1 if emp.is_available_on_date(day_date, day_of_week) else 0
                    )

        return A

    def _calculate_ideal_shifts(self, E, T) -> Dict[str, float]:
        """Calculate ideal shifts per employee based on availability."""
        cfg = self.config
        ideal_shifts = {}

        for team_name in T:
            team = cfg.get_team(team_name)
            team_employees = [emp.name for emp in cfg.employees_in_team(team_name)]

            # Total available days for this team
            total_team_availability = sum(
                self.available_days[emp_name] for emp_name in team_employees
            )

            # Target shifts for this team
            target_team_shifts = team.target_percentage * self.total_shifts_required

            # Distribute proportionally
            for emp_name in team_employees:
                if total_team_availability > 0:
                    ideal = (
                        self.available_days[emp_name] / total_team_availability
                    ) * target_team_shifts
                else:
                    ideal = 0
                ideal_shifts[emp_name] = ideal

        return ideal_shifts

    def _add_fairness_objective(self, E) -> List:
        """Add fairness terms (absolute deviation from ideal)."""
        fairness_terms = []

        for emp_name in E:
            ideal = self.ideal_shifts[emp_name]
            Z_i = pl.LpVariable(f"Z_{emp_name}", lowBound=0)

            self.prob += Z_i >= ideal - self.S[emp_name]
            self.prob += Z_i >= self.S[emp_name] - ideal

            fairness_terms.append(Z_i)

        return fairness_terms

    def _add_staffing_constraints(self, D, E) -> None:
        """Add daily staffing requirement constraints."""
        cfg = self.config

        for k in D:
            day_of_week = (cfg.start_date.weekday() + k) % 7
            required = cfg.staffing_requirements[day_of_week]

            self.prob += (
                pl.lpSum(self.x[emp_name][k] for emp_name in E) == required,
                f"Staffing_Day_{k}",
            )

    def _add_availability_constraints(self, D, E) -> None:
        """Add availability constraints (vacation and part-time)."""
        for emp_name in E:
            for k in D:
                if self.A[emp_name][k] == 0:
                    self.prob += (
                        self.x[emp_name][k] == 0,
                        f"Availability_{emp_name}_Day_{k}",
                    )

    def _add_shift_counting_constraints(self, D, E, T) -> None:
        """Add shift counting constraints for employees and teams."""
        cfg = self.config

        # Employee shift counts
        for emp_name in E:
            self.prob += (
                self.S[emp_name] == pl.lpSum(self.x[emp_name][k] for k in D),
                f"ShiftCount_{emp_name}",
            )

        # Team shift counts
        for team_name in T:
            team_employees = [emp.name for emp in cfg.employees_in_team(team_name)]
            self.prob += (
                self.S_t[team_name]
                == pl.lpSum(self.S[emp_name] for emp_name in team_employees),
                f"TeamShiftCount_{team_name}",
            )

    def _add_team_distribution_constraints(self, T) -> None:
        """Add team distribution target constraints."""
        cfg = self.config

        for team_name in T:
            team = cfg.get_team(team_name)
            target_shifts = team.target_percentage * self.total_shifts_required

            # Absolute deviation
            self.prob += (
                self.D_t[team_name] >= target_shifts - self.S_t[team_name],
                f"TeamDev_Upper_{team_name}",
            )
            self.prob += (
                self.D_t[team_name] >= self.S_t[team_name] - target_shifts,
                f"TeamDev_Lower_{team_name}",
            )

    def _add_consecutive_shift_constraints(self, E, D) -> None:
        """Add soft constraints for consecutive shifts."""
        max_consec = self.config.max_consecutive_shifts
        window = max_consec + 1  # Window size to detect violations

        for emp_name in E:
            for k in D:
                if k + max_consec < self.config.total_days:
                    # If (max_consec + 1) consecutive shifts, C[i][k] must be 1
                    self.prob += (
                        self.C[emp_name][k]
                        >= pl.lpSum(self.x[emp_name][k + j] for j in range(window))
                        - max_consec,
                        f"ConsecutiveDetect_{emp_name}_Day_{k}",
                    )

    def _add_weekly_shift_constraints(self, E, weeks) -> None:
        """Add soft constraints penalizing excess shifts per week.

        For each employee and week, W[employee][week] captures the number of
        shifts above max_shifts_per_week. The objective function penalizes
        this excess linearly (2 extra shifts = 2x penalty).

        Args:
            E: List of employee names
            weeks: Range of week indices
        """
        max_weekly = self.config.max_shifts_per_week

        for emp_name in E:
            for week_idx in weeks:
                week_start_day = week_idx * 7
                days_in_week = range(week_start_day, week_start_day + 7)

                shifts_this_week = pl.lpSum(
                    self.x[emp_name][day] for day in days_in_week
                )

                # W >= shifts - max captures excess; W >= 0 from variable bounds
                # Minimization ensures W equals exactly max(0, shifts - max)
                self.prob += (
                    self.W[emp_name][week_idx] >= shifts_this_week - max_weekly,
                    f"WeeklyExcess_{emp_name}_Week_{week_idx}",
                )

    def _add_same_day_consecutive_weeks_constraints(self, E, weeks) -> None:
        """Add soft constraints penalizing same day-of-week in consecutive weeks.

        For each employee, week pair (w, w+1), and day-of-week, R[e][w][d] is 1
        if the employee works on day d in both week w and week w+1.

        Args:
            E: List of employee names
            weeks: Range of week indices (0 to duration_weeks-2)
        """
        for emp_name in E:
            for week_idx in weeks:
                for day_of_week in range(7):
                    # Day index in week w and week w+1
                    day_in_week_w = week_idx * 7 + day_of_week
                    day_in_week_w_plus_1 = (week_idx + 1) * 7 + day_of_week

                    # R >= x[week_w] + x[week_w+1] - 1
                    # If both are 1, R must be >= 1; otherwise R can be 0
                    self.prob += (
                        self.R[emp_name][week_idx][day_of_week]
                        >= self.x[emp_name][day_in_week_w]
                        + self.x[emp_name][day_in_week_w_plus_1]
                        - 1,
                        f"SameDayConsec_{emp_name}_Week_{week_idx}_Day_{day_of_week}",
                    )

    def _solve(self) -> None:
        """Solve the linear programming problem."""
        self.prob.solve(pl.PULP_CBC_CMD(msg=0))

    def _calculate_consecutive_stats(
        self, assigned_days: List[int], all_days: range, max_allowed: int
    ) -> tuple[int, int]:
        """Calculate consecutive shift statistics for an employee.

        Args:
            assigned_days: List of day indices where employee is assigned
            all_days: Range of all days in the schedule
            max_allowed: Maximum consecutive shifts before violation

        Returns:
            Tuple of (max_consecutive_shifts, violation_count)
        """
        assigned_set = set(assigned_days)
        max_consecutive = 0
        violations = 0
        consecutive_count = 0

        for day in all_days:
            if day in assigned_set:
                consecutive_count += 1
                max_consecutive = max(max_consecutive, consecutive_count)
            else:
                if consecutive_count > max_allowed:
                    violations += 1
                consecutive_count = 0

        # Check final streak
        if consecutive_count > max_allowed:
            violations += 1

        return max_consecutive, violations

    def _calculate_weekly_stats(
        self, assigned_days: List[int], num_weeks: int, max_allowed: int
    ) -> tuple[List[int], int]:
        """Calculate weekly shift statistics for an employee.

        Args:
            assigned_days: List of day indices where employee is assigned
            num_weeks: Number of weeks in the schedule
            max_allowed: Maximum shifts per week before violation

        Returns:
            Tuple of (shifts_per_week_list, violation_count)
        """
        assigned_set = set(assigned_days)
        weekly_shifts = []
        violations = 0

        for week_idx in range(num_weeks):
            week_start = week_idx * 7
            shifts_in_week = sum(
                1 for day in range(week_start, week_start + 7) if day in assigned_set
            )
            weekly_shifts.append(shifts_in_week)

            if shifts_in_week > max_allowed:
                violations += 1

        return weekly_shifts, violations

    def _calculate_same_day_consecutive_weeks_violations(
        self, assigned_days: List[int], num_weeks: int
    ) -> int:
        """Calculate same day-of-week consecutive weeks violations.

        Counts how many times an employee works on the same day-of-week
        in two consecutive weeks.

        Args:
            assigned_days: List of day indices where employee is assigned
            num_weeks: Number of weeks in the schedule

        Returns:
            Number of violations (same day in week w and week w+1)
        """
        if num_weeks < 2:
            return 0

        assigned_set = set(assigned_days)
        violations = 0

        for week_idx in range(num_weeks - 1):
            for day_of_week in range(7):
                day_in_week_w = week_idx * 7 + day_of_week
                day_in_week_w_plus_1 = (week_idx + 1) * 7 + day_of_week

                if (
                    day_in_week_w in assigned_set
                    and day_in_week_w_plus_1 in assigned_set
                ):
                    violations += 1

        return violations

    def _extract_results(self) -> ScheduleResult:
        """Extract results from solved problem into ScheduleResult object."""
        cfg = self.config
        D = range(cfg.total_days)
        E = [emp.name for emp in cfg.employees]

        # Extract daily assignments
        daily_assignments = []
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        for k in D:
            day_date = cfg.start_date + timedelta(days=k)
            day_of_week_idx = (cfg.start_date.weekday() + k) % 7
            day_of_week_name = day_names[day_of_week_idx]

            assigned_employees = [
                emp_name for emp_name in E if pl.value(self.x[emp_name][k]) == 1
            ]

            daily_assignments.append(
                DailyAssignment(
                    day_index=k,
                    date=day_date,
                    day_of_week=day_of_week_name,
                    employees=assigned_employees,
                    required=cfg.staffing_requirements[day_of_week_idx],
                    actual=len(assigned_employees),
                )
            )

        # Extract employee schedules
        employee_schedules = []
        max_consec_allowed = cfg.max_consecutive_shifts
        max_weekly_allowed = cfg.max_shifts_per_week

        for emp in cfg.employees:
            assigned_days = [k for k in D if pl.value(self.x[emp.name][k]) == 1]
            actual_shifts = len(assigned_days)

            # Calculate consecutive stats
            max_consecutive, consecutive_violations = self._calculate_consecutive_stats(
                assigned_days, D, max_consec_allowed
            )

            # Calculate weekly stats
            weekly_shifts, weekly_violations = self._calculate_weekly_stats(
                assigned_days, cfg.duration_weeks, max_weekly_allowed
            )

            # Calculate same-day consecutive weeks violations
            same_day_violations = self._calculate_same_day_consecutive_weeks_violations(
                assigned_days, cfg.duration_weeks
            )

            employee_schedules.append(
                EmployeeSchedule(
                    employee=emp,
                    assigned_days=assigned_days,
                    ideal_shifts=self.ideal_shifts[emp.name],
                    actual_shifts=actual_shifts,
                    max_consecutive=max_consecutive,
                    consecutive_violations=consecutive_violations,
                    weekly_shifts=weekly_shifts,
                    weekly_violations=weekly_violations,
                    same_day_consecutive_weeks_violations=same_day_violations,
                )
            )

        # Extract team summaries
        team_summaries = []

        for team in cfg.teams:
            target_shifts = team.target_percentage * self.total_shifts_required
            actual_shifts = pl.value(self.S_t[team.name])
            deviation = pl.value(self.D_t[team.name])

            team_summaries.append(
                TeamSummary(
                    team=team,
                    target_shifts=target_shifts,
                    actual_shifts=actual_shifts,
                    deviation=deviation,
                )
            )

        return ScheduleResult(
            config=cfg,
            status=pl.LpStatus[self.prob.status],
            objective_value=pl.value(self.prob.objective),
            daily_assignments=daily_assignments,
            employee_schedules=employee_schedules,
            team_summaries=team_summaries,
            total_shifts_required=self.total_shifts_required,
        )
