from change_aware.test_selection import TestSelector


def test_test_selector_can_be_instantiated() -> None:
    assert isinstance(TestSelector(), TestSelector)
