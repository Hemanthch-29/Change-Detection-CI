from change_aware.change_detection import ChangeDetector


def test_change_detector_can_be_instantiated() -> None:
    assert isinstance(ChangeDetector(), ChangeDetector)
