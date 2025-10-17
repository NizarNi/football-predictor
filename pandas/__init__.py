from __future__ import annotations

from datetime import datetime
import math
from typing import Iterable, Sequence, TypeVar, Generic

Timestamp = datetime

_T = TypeVar("_T")


class _Iloc(Generic[_T]):
    def __init__(self, data: Sequence[_T]):
        self._data = data

    def __getitem__(self, index: int) -> _T:
        return self._data[index]


class Series(list[_T]):
    def __init__(self, data: Iterable[_T] | None = None):
        super().__init__(data or [])

    @property
    def iloc(self) -> _Iloc[_T]:
        return _Iloc(self)


def isna(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False


def notna(value: object) -> bool:
    return not isna(value)


__all__ = ["Series", "Timestamp", "isna", "notna"]
