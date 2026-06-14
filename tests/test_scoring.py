from fusionbench.scoring import is_correct, normalize


def test_exact_and_substring():
    assert is_correct("The answer is Paris.", "Paris")
    assert not is_correct("London", "Paris")


def test_alias():
    assert is_correct("USA", "United States", aliases=["USA", "US"])
    assert not is_correct("Canada", "United States", aliases=["USA", "US"])


def test_numeric_tolerance():
    assert is_correct("about 42.0 in total", "42")
    assert is_correct("1,234", "1234")          # comma decimal/grouping normalized
    assert not is_correct("about 7", "42")


def test_normalize():
    assert normalize("  Hello, World! ") == "hello world"
