from change_aware.models import ChangedFile


class ChangeDetector:
    def detect(self) -> list[ChangedFile]:
        raise NotImplementedError
