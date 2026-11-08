
-- Q01: Full table scan
SELECT * FROM Employees;

-- Q02: Full department scan
SELECT * FROM Departments;

-- Q03: Full project scan
SELECT * FROM Projects;

-- Q04: Single-column projection
SELECT name FROM Employees;

-- Q05: Multi-column projection
SELECT name, salary FROM Employees;

-- Q06: Equality filter
SELECT * FROM Employees WHERE department_id = 1;

-- Q07: Greater-than filter
SELECT * FROM Employees WHERE salary > 80000;

-- Q08: Less-than filter
SELECT * FROM Employees WHERE salary < 70000;

-- Q09: Greater-than-or-equal filter
SELECT * FROM Employees WHERE salary >= 85000;

-- Q10: Less-than-or-equal filter
SELECT * FROM Employees WHERE salary <= 64000;

-- Q11: Alternative equality filter
SELECT * FROM Employees WHERE department_id = 2;

-- Q12: Combined filter
SELECT * FROM Employees
WHERE department_id = 1 AND salary > 75000;

-- Q13: Combined filter on departments
SELECT * FROM Departments
WHERE budget > 150000 AND budget < 300000;

-- Q14: Limited scan
SELECT * FROM Employees LIMIT 3;

-- Q15: Limited projection
SELECT name FROM Employees LIMIT 5;

-- Q16: Filter with limit
SELECT name FROM Employees WHERE salary > 70000 LIMIT 4;

-- Q17: Zero-row filter
SELECT * FROM Employees WHERE salary > 200000;

-- Q18: All-row filter
SELECT * FROM Employees WHERE salary > 0;

-- Q19: Department budget filter
SELECT name FROM Departments WHERE budget >= 200000;

-- Q20: Project cost filter
SELECT id, cost FROM Projects WHERE cost > 40000;

-- Q21: Employee-to-department equality join
SELECT Employees.name, Departments.name
FROM Employees
JOIN Departments ON Employees.department_id = Departments.id;

-- Q22: Employee-to-department join with filter
SELECT Employees.name, Employees.salary
FROM Employees
JOIN Departments ON Employees.department_id = Departments.id
WHERE Departments.budget > 200000;

-- Q23: Department-to-project equality join
SELECT Departments.name, Projects.cost
FROM Departments
JOIN Projects ON Departments.id = Projects.department_id;

-- Q24: Employee-to-department join with limit
SELECT Employees.name, Departments.name
FROM Employees
JOIN Departments ON Employees.department_id = Departments.id
LIMIT 5;

-- Q25: Three-table equality join
SELECT Employees.name, Departments.name, Projects.cost
FROM Employees
JOIN Departments ON Employees.department_id = Departments.id
JOIN Projects ON Departments.id = Projects.department_id;
