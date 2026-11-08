
CREATE TABLE Departments (
    id INT,
    name VARCHAR(40),
    budget INT
);

CREATE TABLE Employees (
    id INT,
    name VARCHAR(40),
    department_id INT,
    salary INT
);

CREATE TABLE Projects (
    id INT,
    department_id INT,
    cost INT
);

INSERT INTO Departments VALUES (1, 'Engineering', 300000);
INSERT INTO Departments VALUES (2, 'Marketing', 150000);
INSERT INTO Departments VALUES (3, 'Finance', 200000);
INSERT INTO Departments VALUES (4, 'Operations', 180000);
INSERT INTO Departments VALUES (5, 'Research', 250000);

INSERT INTO Employees VALUES (1, 'Alice', 1, 85000);
INSERT INTO Employees VALUES (2, 'Bob', 1, 72000);
INSERT INTO Employees VALUES (3, 'Charlie', 2, 61000);
INSERT INTO Employees VALUES (4, 'Diana', 3, 95000);
INSERT INTO Employees VALUES (5, 'Ethan', 4, 68000);
INSERT INTO Employees VALUES (6, 'Fiona', 5, 88000);
INSERT INTO Employees VALUES (7, 'George', 1, 78000);
INSERT INTO Employees VALUES (8, 'Hannah', 2, 64000);
INSERT INTO Employees VALUES (9, 'Ian', 3, 91000);
INSERT INTO Employees VALUES (10, 'Julia', 5, 82000);

INSERT INTO Projects VALUES (1, 1, 50000);
INSERT INTO Projects VALUES (2, 1, 75000);
INSERT INTO Projects VALUES (3, 2, 30000);
INSERT INTO Projects VALUES (4, 3, 60000);
INSERT INTO Projects VALUES (5, 4, 45000);
INSERT INTO Projects VALUES (6, 5, 90000);
INSERT INTO Projects VALUES (7, 5, 40000);
INSERT INTO Projects VALUES (8, 2, 25000);
