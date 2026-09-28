from change_aware.dependency import DependencyGraph
from change_aware.models import ChangedFile, ImpactedComponent


class ImpactAnalyzer:
    def analyze(
        self, changed_files: list[ChangedFile], graph: DependencyGraph
    ) -> list[ImpactedComponent]:
        raise NotImplementedError
