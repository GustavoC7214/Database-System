from src.lexer.tokenizer import Tokenizer
from src.parser.parser import Parser
from src.parser.tree_printer import print_tree


def test_project_select_tree():
    source = "project[Name](select[Age>30](Employees))"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Project(attrs=[Name])
└── Select(cond=Gt(Attr(Age), Num(30)))
    └── Relation(Employees)"""

    assert tree == expected

def test_binary_expression_tree():
    source = "(A union B) minus (C intersect D)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Minus
├── Union
│   ├── Relation(A)
│   └── Relation(B)
└── Intersect
    ├── Relation(C)
    └── Relation(D)"""

    assert tree == expected

def test_boolean_condition_tree():
    source = "select[not (a=1 and b=2) or c>3](R)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)

    expected = """Select(cond=Or(Not(And(Eq(Attr(a), Num(1)), Eq(Attr(b), Num(2)))), Gt(Attr(c), Num(3))))
└── Relation(R)"""

    assert tree == expected

def test_join_tree():
    source = "Member join[Member.Place=Chapter.Location] Chapter"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Join(cond=Eq(Attr(Member.Place), Attr(Chapter.Location)))
├── Relation(Member)
└── Relation(Chapter)"""
    assert tree == expected

def test_rename_tree():
    source = "rename[E2](Employees)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Rename(name=E2)
└── Relation(Employees)"""

    assert tree == expected

def test_times_tree():
    source = "Employees times Departments"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Times
├── Relation(Employees)
└── Relation(Departments)"""

    assert tree == expected


def test_sort_tree():
    source = "sort[Age asc](Employees)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Sort(attr=Age, direction=asc)
└── Relation(Employees)"""

    assert tree == expected


def test_sort_qualified_attribute_tree():
    source = "sort[Employees.Age desc](Employees)"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Sort(attr=Employees.Age, direction=desc)
└── Relation(Employees)"""

    assert tree == expected


def test_sort_nested_tree():
    source = "sort[Age desc](select[Age>30](Employees))"

    tokens = Tokenizer(source).tokenize()
    result = Parser(tokens).parse()

    tree = print_tree(result)
    expected = """Sort(attr=Age, direction=desc)
└── Select(cond=Gt(Attr(Age), Num(30)))
    └── Relation(Employees)"""

    assert tree == expected