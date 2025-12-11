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

        # Objective function: minimize fairness deviation + penalties
        fairness_terms = self._add_fairness_objective(E)

        self.prob += (
            pl.lpSum(fairness_terms)
            + cfg.penalty_team_deviation * pl.lpSum(self.D_t)
            + cfg.penalty_consecutive_shifts
            * pl.lpSum(self.C[i][k] for i in E for k in D),
            "Total Cost",
        )

        # Add constraints
        self._add_staffing_constraints(D, E)
        self._add_availability_constraints(D, E)
        self._add_shift_counting_constraints(D, E, T)
        self._add_team_distribution_constraints(T)
        self._add_consecutive_shift_constraints(E, D)

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
        """Add soft constraints for consecutive shifts (max 3)."""
        for emp_name in E:
            for k in D:
                if k + 3 < self.config.total_days:
                    # If 4 consecutive shifts, C[i][k] must be 1
                    self.prob += (
                        self.C[emp_name][k]
                        >= (
                            self.x[emp_name][k]
                            + self.x[emp_name][k + 1]
                            + self.x[emp_name][k + 2]
                            + self.x[emp_name][k + 3]
                        )
                        - 3,
                        f"ConsecutiveDetect_{emp_name}_Day_{k}",
                    )

    def _solve(self) -> None:
        """Solve the linear programming problem."""
        self.prob.solve(pl.PULP_CBC_CMD(msg=0))

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

        for emp in cfg.employees:
            assigned_days = [k for k in D if pl.value(self.x[emp.name][k]) == 1]
            actual_shifts = len(assigned_days)

            # Calculate max consecutive and violations
            max_consecutive = 0
            violations_count = 0
            consecutive_count = 0

            for k in D:
                if pl.value(self.x[emp.name][k]) == 1:
                    consecutive_count += 1
                    max_consecutive = max(max_consecutive, consecutive_count)
                else:
                    if consecutive_count > 3:
                        violations_count += 1
                    consecutive_count = 0

            if consecutive_count > 3:
                violations_count += 1

            employee_schedules.append(
                EmployeeSchedule(
                    employee=emp,
                    assigned_days=assigned_days,
                    ideal_shifts=self.ideal_shifts[emp.name],
                    actual_shifts=actual_shifts,
                    max_consecutive=max_consecutive,
                    violations_count=violations_count,
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
