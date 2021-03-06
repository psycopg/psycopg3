"""
Support for range types adaptation.
"""

# Copyright (C) 2020-2021 The Psycopg Team

import re
from typing import Any, Dict, Generic, Optional, Sequence, TypeVar, Type, Union
from typing import cast, Tuple, TYPE_CHECKING
from decimal import Decimal
from datetime import date, datetime

from .. import sql
from .. import errors as e
from ..pq import Format
from ..oids import builtins, TypeInfo, INVALID_OID
from ..adapt import Buffer, Dumper, Loader, Format as Pg3Format
from ..proto import AdaptContext

from . import array
from .composite import SequenceDumper, BaseCompositeLoader

if TYPE_CHECKING:
    from ..connection import Connection, AsyncConnection

T = TypeVar("T")


class Range(Generic[T]):
    """Python representation for a PostgreSQL |range|_ type.

    :param lower: lower bound for the range. `!None` means unbound
    :param upper: upper bound for the range. `!None` means unbound
    :param bounds: one of the literal strings ``()``, ``[)``, ``(]``, ``[]``,
        representing whether the lower or upper bounds are included
    :param empty: if `!True`, the range is empty

    """

    __slots__ = ("_lower", "_upper", "_bounds")

    def __init__(
        self,
        lower: Optional[T] = None,
        upper: Optional[T] = None,
        bounds: str = "[)",
        empty: bool = False,
    ):
        if not empty:
            if bounds not in ("[)", "(]", "()", "[]"):
                raise ValueError("bound flags not valid: %r" % bounds)

            self._lower = lower
            self._upper = upper
            self._bounds = bounds
        else:
            self._lower = self._upper = None
            self._bounds = ""

    def __repr__(self) -> str:
        if not self._bounds:
            return "%s(empty=True)" % self.__class__.__name__
        else:
            return "%s(%r, %r, %r)" % (
                self.__class__.__name__,
                self._lower,
                self._upper,
                self._bounds,
            )

    def __str__(self) -> str:
        if not self._bounds:
            return "empty"

        items = [
            self._bounds[0],
            str(self._lower),
            ", ",
            str(self._upper),
            self._bounds[1],
        ]
        return "".join(items)

    @property
    def lower(self) -> Optional[T]:
        """The lower bound of the range. `!None` if empty or unbound."""
        return self._lower

    @property
    def upper(self) -> Optional[T]:
        """The upper bound of the range. `!None` if empty or unbound."""
        return self._upper

    @property
    def isempty(self) -> bool:
        """`!True` if the range is empty."""
        return not self._bounds

    @property
    def lower_inf(self) -> bool:
        """`!True` if the range doesn't have a lower bound."""
        if not self._bounds:
            return False
        return self._lower is None

    @property
    def upper_inf(self) -> bool:
        """`!True` if the range doesn't have an upper bound."""
        if not self._bounds:
            return False
        return self._upper is None

    @property
    def lower_inc(self) -> bool:
        """`!True` if the lower bound is included in the range."""
        if not self._bounds or self._lower is None:
            return False
        return self._bounds[0] == "["

    @property
    def upper_inc(self) -> bool:
        """`!True` if the upper bound is included in the range."""
        if not self._bounds or self._upper is None:
            return False
        return self._bounds[1] == "]"

    def __contains__(self, x: T) -> bool:
        if not self._bounds:
            return False

        if self._lower is not None:
            if self._bounds[0] == "[":
                # It doesn't seem that Python has an ABC for ordered types.
                if x < self._lower:  # type: ignore[operator]
                    return False
            else:
                if x <= self._lower:  # type: ignore[operator]
                    return False

        if self._upper is not None:
            if self._bounds[1] == "]":
                if x > self._upper:  # type: ignore[operator]
                    return False
            else:
                if x >= self._upper:  # type: ignore[operator]
                    return False

        return True

    def __bool__(self) -> bool:
        return bool(self._bounds)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Range):
            return False
        return (
            self._lower == other._lower
            and self._upper == other._upper
            and self._bounds == other._bounds
        )

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash((self._lower, self._upper, self._bounds))

    # as the postgres docs describe for the server-side stuff,
    # ordering is rather arbitrary, but will remain stable
    # and consistent.

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, Range):
            return NotImplemented
        for attr in ("_lower", "_upper", "_bounds"):
            self_value = getattr(self, attr)
            other_value = getattr(other, attr)
            if self_value == other_value:
                pass
            elif self_value is None:
                return True
            elif other_value is None:
                return False
            else:
                return cast(bool, self_value < other_value)
        return False

    def __le__(self, other: Any) -> bool:
        if self == other:
            return True
        else:
            return self.__lt__(other)

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, Range):
            return other.__lt__(self)
        else:
            return NotImplemented

    def __ge__(self, other: Any) -> bool:
        if self == other:
            return True
        else:
            return self.__gt__(other)

    def __getstate__(self) -> Dict[str, Any]:
        return {
            slot: getattr(self, slot)
            for slot in self.__slots__
            if hasattr(self, slot)
        }

    def __setstate__(self, state: Dict[str, Any]) -> None:
        for slot, value in state.items():
            setattr(self, slot, value)


class RangeDumper(SequenceDumper):
    """
    Dumper for range types.

    The dumper can upgrade to one specific for a different range type.
    """

    format = Format.TEXT

    def __init__(self, cls: type, context: Optional[AdaptContext] = None):
        super().__init__(cls, context)
        self.sub_dumper: Optional[Dumper] = None

    def dump(self, obj: Range[Any]) -> bytes:
        if not obj:
            return b"empty"
        else:
            return self._dump_sequence(
                (obj.lower, obj.upper),
                b"[" if obj.lower_inc else b"(",
                b"]" if obj.upper_inc else b")",
                b",",
            )

    _re_needs_quotes = re.compile(br'[",\\\s()\[\]]')

    def get_key(self, obj: Range[Any], format: Pg3Format) -> Tuple[type, ...]:
        item = self._get_item(obj)
        if item is not None:
            # TODO: binary range support
            sd = self._tx.get_dumper(item, Pg3Format.TEXT)
            return (self.cls, sd.cls)
        else:
            return (self.cls,)

    def upgrade(self, obj: Range[Any], format: Pg3Format) -> "RangeDumper":
        item = self._get_item(obj)
        if item is None:
            return RangeDumper(self.cls)

        # TODO: binary range support
        sd = self._tx.get_dumper(item, Pg3Format.TEXT)
        dumper = type(self)(self.cls, self._tx)
        dumper.sub_dumper = sd
        if not isinstance(item, int):
            dumper.oid = self._get_range_oid(sd.oid)
        else:
            # postgres won't cast int4range -> int8range so we must use
            # text format and unknown oid here
            dumper.oid = INVALID_OID
        return dumper

    def _get_item(self, obj: Range[Any]) -> Any:
        """
        Return a member representative of the range
        """
        rv = obj.lower
        return rv if rv is not None else obj.upper

    def _get_range_oid(self, sub_oid: int) -> int:
        """
        Return the oid of the range from the oid of its elements.

        Raise InterfaceError if not found.

        TODO: we shouldn't consider builtins only, but other adaptation
        contexts too
        """
        info = builtins.get_range(sub_oid)
        return info.oid if info else INVALID_OID


class RangeLoader(BaseCompositeLoader, Generic[T]):
    """Generic loader for a range.

    Subclasses shoud specify the oid of the subtype and the class to load.
    """

    subtype_oid: int

    def load(self, data: Buffer) -> Range[T]:
        if data == b"empty":
            return Range(empty=True)

        cast = self._tx.get_loader(self.subtype_oid, format=Format.TEXT).load
        bounds = _int2parens[data[0]] + _int2parens[data[-1]]
        min, max = (
            cast(token) if token is not None else None
            for token in self._parse_record(data[1:-1])
        )
        return Range(min, max, bounds)


_int2parens = {ord(c): c for c in "[]()"}


# Loaders for builtin range types


class Int4RangeLoader(RangeLoader[int]):
    subtype_oid = builtins["int4"].oid


class Int8RangeLoader(RangeLoader[int]):
    subtype_oid = builtins["int8"].oid


class NumericRangeLoader(RangeLoader[Decimal]):
    subtype_oid = builtins["numeric"].oid


class DateRangeLoader(RangeLoader[date]):
    subtype_oid = builtins["date"].oid


class TimestampRangeLoader(RangeLoader[datetime]):
    subtype_oid = builtins["timestamp"].oid


class TimestampTZRangeLoader(RangeLoader[datetime]):
    subtype_oid = builtins["timestamptz"].oid


class RangeInfo(TypeInfo):
    """Manage information about a range type.

    The class allows to:

    - read information about a range type using `fetch()` and `fetch_async()`
    - configure a composite type adaptation using `register()`
    """

    @classmethod
    def fetch(
        cls, conn: "Connection", name: Union[str, sql.Identifier]
    ) -> Optional["RangeInfo"]:
        if isinstance(name, sql.Composable):
            name = name.as_string(conn)
        cur = conn.cursor(binary=True)
        cur.execute(cls._info_query, {"name": name})
        recs = cur.fetchall()
        return cls._from_records(recs)

    @classmethod
    async def fetch_async(
        cls, conn: "AsyncConnection", name: Union[str, sql.Identifier]
    ) -> Optional["RangeInfo"]:
        if isinstance(name, sql.Composable):
            name = name.as_string(conn)
        cur = await conn.cursor(binary=True)
        await cur.execute(cls._info_query, {"name": name})
        recs = await cur.fetchall()
        return cls._from_records(recs)

    def register(
        self,
        context: Optional[AdaptContext] = None,
    ) -> None:
        # A new dumper is not required. However TODO we will need to register
        # the dumper in the adapters type registry, when we have one.

        # generate and register a customized text loader
        loader: Type[Loader] = type(
            f"{self.name.title()}Loader",
            (RangeLoader,),
            {"subtype_oid": self.range_subtype},
        )
        loader.register(self.oid, context=context)

        if self.array_oid:
            array.register(
                self.array_oid, self.oid, context=context, name=self.name
            )

    @classmethod
    def _from_records(cls, recs: Sequence[Any]) -> Optional["RangeInfo"]:
        if not recs:
            return None
        if len(recs) > 1:
            raise e.ProgrammingError(
                f"found {len(recs)} different ranges named {recs[0][0]}"
            )

        name, oid, array_oid, subtype = recs[0]
        return cls(name, oid, array_oid, subtype)

    _info_query = """\
select t.typname as name, t.oid as oid, t.typarray as array_oid,
    r.rngsubtype as range_subtype
from pg_type t
join pg_range r on t.oid = r.rngtypid
where t.oid = %(name)s::regtype
"""
