# Steward Shift - A Shift Scheduling Planner

- For a shift we have a certain number of people we need to reach for a day
  (e.g. on monday 3 people meed to do that shift, rest of the week only 2
  persons are needed).
- Some employees have vacations we want to be able to specify. Multiple
  vacations per person per period are possible. One day vacations are also
  possible.
- Some employees are only part time here. Part time should be taken into
  account, such that they do less that shift.
- There are two teams are doing that shift, team A should do 67% of all shifts,
  team B should do 33% of all shifts (these distributions should be variable).
- The shifts should be distributed equally among all employees, according to
  the team membership.
- It is not feasible for a person to do more than 3 shifts in a row. This is
  modeled as a soft boundary.
- We want to be able to plan for K month periods (e.g. K=3).



- Max 1x per week
  - If 2 days, then not consecutive
- not same person always mondays and not always fridays
- If fridays, not monday
- teamdays: members of a certain team should not have shift on that teamday
  
- output as csv  
  - like a calendar 
  - modular, s.t. we can push to teams
