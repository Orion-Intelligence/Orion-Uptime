from pydantic import BaseModel


class PersistedModel(BaseModel):
    id: str | None = None

    @property
    def persisted_id(self) -> str:
        if self.id is None:
            raise ValueError("The document has not been persisted yet.")
        return self.id
