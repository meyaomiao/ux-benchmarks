from typing import TypeVar, Generic, Sequence
from pydantic import BaseModel, Field

T = TypeVar("T")


class PageParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel, Generic[T]):
    items: Sequence[T]
    total: int
    limit: int
    offset: int
    has_next: bool

    @classmethod
    def create(cls, items: Sequence[T], total: int, params: PageParams) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            limit=params.limit,
            offset=params.offset,
            has_next=params.offset + params.limit < total,
        )
