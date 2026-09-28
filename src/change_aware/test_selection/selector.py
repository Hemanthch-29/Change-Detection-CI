from change_aware.models import ImpactedComponent, TestSelectionResult


class TestSelector:
    __test__ = False  # prevent pytest from collecting this class

    def select(self, impacted: list[ImpactedComponent]) -> TestSelectionResult:
        raise NotImplementedError
