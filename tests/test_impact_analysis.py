from change_aware.impact import ImpactAnalyzer


def test_impact_analyzer_can_be_instantiated() -> None:
    assert isinstance(ImpactAnalyzer(), ImpactAnalyzer)
