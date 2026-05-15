from oxidant.analysis.generate_skeleton import map_python_type


def test_primitives():
    assert map_python_type("int") == "i64"
    assert map_python_type("float") == "f64"
    assert map_python_type("str") == "String"
    assert map_python_type("bool") == "bool"
    assert map_python_type("bytes") == "Vec<u8>"
    assert map_python_type("None") == "()"


def test_list():
    assert map_python_type("list[int]") == "Vec<i64>"
    assert map_python_type("List[str]") == "Vec<String>"


def test_dict():
    assert map_python_type("dict[str, int]") == "std::collections::HashMap<String, i64>"
    assert map_python_type("Dict[str, float]") == "std::collections::HashMap<String, f64>"


def test_set():
    assert map_python_type("set[str]") == "std::collections::HashSet<String>"


def test_optional_bracket():
    assert map_python_type("Optional[int]") == "Option<i64>"
    assert map_python_type("Optional[str]") == "Option<String>"


def test_optional_union_syntax():
    assert map_python_type("int | None") == "Option<i64>"
    assert map_python_type("None | str") == "Option<String>"


def test_tuple_two():
    assert map_python_type("tuple[str, float]") == "(String, f64)"
    assert map_python_type("Tuple[int, int]") == "(i64, i64)"


def test_any():
    assert map_python_type("Any") == "serde_json::Value"


def test_unknown_type():
    assert map_python_type("MyClass") == "serde_json::Value"


def test_known_class():
    assert map_python_type("MyClass", known_classes={"MyClass"}) == "Rc<RefCell<MyClass>>"


def test_nested_list_optional():
    assert map_python_type("list[Optional[int]]") == "Vec<Option<i64>>"
