class EntityNotFoundError(Exception):
    def __init__(self, entity: str, identifier: str) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} '{identifier}' was not found")


class DuplicateEntityError(Exception):
    pass


class ClinicalApiError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 400) -> None:
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)
