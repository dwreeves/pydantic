"""
Bucket of reusable internal utilities.
"""
from __future__ import annotations as _annotations

import keyword
import weakref
from collections import OrderedDict, defaultdict, deque
from copy import deepcopy
from itertools import zip_longest
from types import BuiltinFunctionType, CodeType, FunctionType, GeneratorType, LambdaType, ModuleType
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Any,
    Callable,
    Collection,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    NoReturn,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from typing_extensions import Annotated

from pydantic.errors import ConfigError

from . import _repr
from ._typing_extra import (
    NoneType,
    WithArgsTypes,
    all_literal_values,
    get_args,
    get_origin,
    is_literal_type,
    origin_is_union,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ..dataclasses import Dataclass
    from ..main import BaseModel
    from ._typing_extra import AbstractSetIntStr, DictIntStrAny, IntStr, MappingIntStrAny

__all__ = (
    'import_string',
    'sequence_like',
    'validate_field_name',
    'lenient_isinstance',
    'lenient_issubclass',
    'in_ipython',
    'is_valid_identifier',
    'deep_update',
    'update_not_none',
    'almost_equal_floats',
    'get_model',
    'to_camel',
    'is_valid_field',
    'smart_deepcopy',
    'PyObjectStr',
    'GetterDict',
    'ValueItems',
    'ClassAttribute',
    'path_type',
    'ROOT_KEY',
    'get_unique_discriminator_alias',
    'get_discriminator_alias_and_values',
    'DUNDER_ATTRIBUTES',
    'LimitedDict',
    'dict_not_none',
)

ROOT_KEY = '__root__'
# these are types that are returned unchanged by deepcopy
IMMUTABLE_NON_COLLECTIONS_TYPES: Set[Type[Any]] = {
    int,
    float,
    complex,
    str,
    bool,
    bytes,
    type,
    NoneType,
    FunctionType,
    BuiltinFunctionType,
    LambdaType,
    weakref.ref,
    CodeType,
    # note: including ModuleType will differ from behaviour of deepcopy by not producing error.
    # It might be not a good idea in general, but considering that this function used only internally
    # against default values of fields, this will allow to actually have a field with module as default value
    ModuleType,
    NotImplemented.__class__,
    Ellipsis.__class__,
}

# these are types that if empty, might be copied with simple copy() instead of deepcopy()
BUILTIN_COLLECTIONS: Set[Type[Any]] = {
    list,
    set,
    tuple,
    frozenset,
    dict,
    OrderedDict,
    defaultdict,
    deque,
}


def import_string(dotted_path: str) -> Any:
    """
    Stolen approximately from django. Import a dotted module path and return the attribute/class designated by the
    last name in the path. Raise ImportError if the import fails.
    """
    from importlib import import_module

    try:
        module_path, class_name = dotted_path.strip(' ').rsplit('.', 1)
    except ValueError as e:
        raise ImportError(f'"{dotted_path}" doesn\'t look like a module path') from e

    module = import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ImportError(f'Module "{module_path}" does not define a "{class_name}" attribute') from e


def sequence_like(v: Any) -> bool:
    return isinstance(v, (list, tuple, set, frozenset, GeneratorType, deque))


def validate_field_name(bases: List[Type['BaseModel']], field_name: str) -> None:
    """
    Ensure that the field's name does not shadow an existing attribute of the model.
    """
    for base in bases:
        if getattr(base, field_name, None):
            raise NameError(
                f'Field name "{field_name}" shadows a BaseModel attribute; '
                f'use a different field name with "alias=\'{field_name}\'".'
            )


def lenient_isinstance(o: Any, class_or_tuple: Union[Type[Any], Tuple[Type[Any], ...], None]) -> bool:
    try:
        return isinstance(o, class_or_tuple)  # type: ignore[arg-type]
    except TypeError:
        return False


def lenient_issubclass(cls: Any, class_or_tuple: Any) -> bool:
    try:
        return isinstance(cls, type) and issubclass(cls, class_or_tuple)
    except TypeError:
        if isinstance(cls, WithArgsTypes):
            return False
        raise  # pragma: no cover


def in_ipython() -> bool:
    """
    Check whether we're in an ipython environment, including jupyter notebooks.
    """
    try:
        eval('__IPYTHON__')
    except NameError:
        return False
    else:  # pragma: no cover
        return True


def is_valid_identifier(identifier: str) -> bool:
    """
    Checks that a string is a valid identifier and not a Python keyword.
    :param identifier: The identifier to test.
    :return: True if the identifier is valid.
    """
    return identifier.isidentifier() and not keyword.iskeyword(identifier)


KeyType = TypeVar('KeyType')


def deep_update(mapping: Dict[KeyType, Any], *updating_mappings: Dict[KeyType, Any]) -> Dict[KeyType, Any]:
    updated_mapping = mapping.copy()
    for updating_mapping in updating_mappings:
        for k, v in updating_mapping.items():
            if k in updated_mapping and isinstance(updated_mapping[k], dict) and isinstance(v, dict):
                updated_mapping[k] = deep_update(updated_mapping[k], v)
            else:
                updated_mapping[k] = v
    return updated_mapping


def dict_not_none(__pos: Dict[str, Any] = None, **kwargs: Any) -> Dict[str, Any]:
    return {k: v for k, v in (__pos or kwargs).items() if v is not None}


def update_not_none(mapping: Dict[Any, Any], **update: Any) -> None:
    mapping.update({k: v for k, v in update.items() if v is not None})


def almost_equal_floats(value_1: float, value_2: float, *, delta: float = 1e-8) -> bool:
    """
    Return True if two floats are almost equal
    """
    return abs(value_1 - value_2) <= delta


def get_model(obj: Union[Type['BaseModel'], Type['Dataclass']]) -> Type['BaseModel']:
    from ..main import BaseModel

    try:
        model_cls = obj.__pydantic_model__  # type: ignore
    except AttributeError:
        model_cls = obj

    if not issubclass(model_cls, BaseModel):
        raise TypeError('Unsupported type, must be either BaseModel or dataclass')
    return model_cls


def to_camel(string: str) -> str:
    return ''.join(word.capitalize() for word in string.split('_'))


def to_lower_camel(string: str) -> str:
    if len(string) >= 1:
        pascal_string = to_camel(string)
        return pascal_string[0].lower() + pascal_string[1:]
    return string.lower()


T = TypeVar('T')


def unique_list(
    input_list: Union[List[T], Tuple[T, ...]],
    *,
    name_factory: Callable[[T], str] = str,
) -> List[T]:
    """
    Make a list unique while maintaining order.
    We update the list if another one with the same name is set
    (e.g. root validator overridden in subclass)
    """
    result: List[T] = []
    result_names: List[str] = []
    for v in input_list:
        v_name = name_factory(v)
        if v_name not in result_names:
            result_names.append(v_name)
            result.append(v)
        else:
            result[result_names.index(v_name)] = v

    return result


class PyObjectStr(str):
    """
    String class where repr doesn't include quotes. Useful with Representation when you want to return a string
    representation of something that valid (or pseudo-valid) python.
    """

    def __repr__(self) -> str:
        return str(self)


class GetterDict(_repr.Representation):
    """
    Hack to make object's smell just enough like dicts for validate_model.

    We can't inherit from Mapping[str, Any] because it upsets cython so we have to implement all methods ourselves.
    """

    __slots__ = ('_obj',)

    def __init__(self, obj: Any):
        self._obj = obj

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self._obj, key)
        except AttributeError as e:
            raise KeyError(key) from e

    def get(self, key: Any, default: Any = None) -> Any:
        return getattr(self._obj, key, default)

    def extra_keys(self) -> Set[Any]:
        """
        We don't want to get any other attributes of obj if the model didn't explicitly ask for them
        """
        return set()

    def keys(self) -> List[Any]:
        """
        Keys of the pseudo dictionary, uses a list not set so order information can be maintained like python
        dictionaries.
        """
        return list(self)

    def values(self) -> List[Any]:
        return [self[k] for k in self]

    def items(self) -> Iterator[Tuple[str, Any]]:
        for k in self:
            yield k, self.get(k)

    def __iter__(self) -> Iterator[str]:
        for name in dir(self._obj):
            if not name.startswith('_'):
                yield name

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, item: Any) -> bool:
        return item in self.keys()

    def __eq__(self, other: Any) -> bool:
        return dict(self) == dict(other.items())

    def __repr_args__(self) -> _repr.ReprArgs:
        return [(None, dict(self))]

    def __repr_name__(self) -> str:
        return f'GetterDict[{_repr.display_as_type(self._obj)}]'


class ValueItems(_repr.Representation):
    """
    Class for more convenient calculation of excluded or included fields on values.
    """

    __slots__ = ('_items', '_type')

    def __init__(self, value: Any, items: Union['AbstractSetIntStr', 'MappingIntStrAny']) -> None:
        items = self._coerce_items(items)

        if isinstance(value, (list, tuple)):
            items = self._normalize_indexes(items, len(value))

        self._items: 'MappingIntStrAny' = items

    def is_excluded(self, item: Any) -> bool:
        """
        Check if item is fully excluded.

        :param item: key or index of a value
        """
        return self.is_true(self._items.get(item))

    def is_included(self, item: Any) -> bool:
        """
        Check if value is contained in self._items

        :param item: key or index of value
        """
        return item in self._items

    def for_element(self, e: 'IntStr') -> Optional[Union['AbstractSetIntStr', 'MappingIntStrAny']]:
        """
        :param e: key or index of element on value
        :return: raw values for element if self._items is dict and contain needed element
        """

        item = self._items.get(e)
        return item if not self.is_true(item) else None

    def _normalize_indexes(self, items: 'MappingIntStrAny', v_length: int) -> 'DictIntStrAny':
        """
        :param items: dict or set of indexes which will be normalized
        :param v_length: length of sequence indexes of which will be

        >>> self._normalize_indexes({0: True, -2: True, -1: True}, 4)
        {0: True, 2: True, 3: True}
        >>> self._normalize_indexes({'__all__': True}, 4)
        {0: True, 1: True, 2: True, 3: True}
        """

        normalized_items: 'DictIntStrAny' = {}
        all_items = None
        for i, v in items.items():
            if not (isinstance(v, Mapping) or isinstance(v, AbstractSet) or self.is_true(v)):
                raise TypeError(f'Unexpected type of exclude value for index "{i}" {v.__class__}')
            if i == '__all__':
                all_items = self._coerce_value(v)
                continue
            if not isinstance(i, int):
                raise TypeError(
                    'Excluding fields from a sequence of sub-models or dicts must be performed index-wise: '
                    'expected integer keys or keyword "__all__"'
                )
            normalized_i = v_length + i if i < 0 else i
            normalized_items[normalized_i] = self.merge(v, normalized_items.get(normalized_i))

        if not all_items:
            return normalized_items
        if self.is_true(all_items):
            for i in range(v_length):
                normalized_items.setdefault(i, ...)
            return normalized_items
        for i in range(v_length):
            normalized_item = normalized_items.setdefault(i, {})
            if not self.is_true(normalized_item):
                normalized_items[i] = self.merge(all_items, normalized_item)
        return normalized_items

    @classmethod
    def merge(cls, base: Any, override: Any, intersect: bool = False) -> Any:
        """
        Merge a ``base`` item with an ``override`` item.

        Both ``base`` and ``override`` are converted to dictionaries if possible.
        Sets are converted to dictionaries with the sets entries as keys and
        Ellipsis as values.

        Each key-value pair existing in ``base`` is merged with ``override``,
        while the rest of the key-value pairs are updated recursively with this function.

        Merging takes place based on the "union" of keys if ``intersect`` is
        set to ``False`` (default) and on the intersection of keys if
        ``intersect`` is set to ``True``.
        """
        override = cls._coerce_value(override)
        base = cls._coerce_value(base)
        if override is None:
            return base
        if cls.is_true(base) or base is None:
            return override
        if cls.is_true(override):
            return base if intersect else override

        # intersection or union of keys while preserving ordering:
        if intersect:
            merge_keys = [k for k in base if k in override] + [k for k in override if k in base]
        else:
            merge_keys = list(base) + [k for k in override if k not in base]

        merged: 'DictIntStrAny' = {}
        for k in merge_keys:
            merged_item = cls.merge(base.get(k), override.get(k), intersect=intersect)
            if merged_item is not None:
                merged[k] = merged_item

        return merged

    @staticmethod
    def _coerce_items(items: Union['AbstractSetIntStr', 'MappingIntStrAny']) -> 'MappingIntStrAny':
        if isinstance(items, Mapping):
            pass
        elif isinstance(items, AbstractSet):
            items = dict.fromkeys(items, ...)
        else:
            class_name = getattr(items, '__class__', '???')
            assert_never(
                items,
                f'Unexpected type of exclude value {class_name}',
            )
        return items

    @classmethod
    def _coerce_value(cls, value: Any) -> Any:
        if value is None or cls.is_true(value):
            return value
        return cls._coerce_items(value)

    @staticmethod
    def is_true(v: Any) -> bool:
        return v is True or v is ...

    def __repr_args__(self) -> _repr.ReprArgs:
        return [(None, self._items)]


if TYPE_CHECKING:

    def ClassAttribute(name: str, value: T) -> T:
        ...

else:

    class ClassAttribute:
        """
        Hide class attribute from its instances
        """

        __slots__ = 'name', 'value'

        def __init__(self, name: str, value: Any) -> None:
            self.name = name
            self.value = value

        def __get__(self, instance: Any, owner: Type[Any]) -> None:
            if instance is None:
                return self.value
            raise AttributeError(f'{self.name!r} attribute of {owner.__name__!r} is class-only')


path_types = {
    'is_dir': 'directory',
    'is_file': 'file',
    'is_mount': 'mount point',
    'is_symlink': 'symlink',
    'is_block_device': 'block device',
    'is_char_device': 'char device',
    'is_fifo': 'FIFO',
    'is_socket': 'socket',
}


def path_type(p: 'Path') -> str:
    """
    Find out what sort of thing a path is.
    """
    assert p.exists(), 'path does not exist'
    for method, name in path_types.items():
        if getattr(p, method)():
            return name

    return 'unknown'


Obj = TypeVar('Obj')


def smart_deepcopy(obj: Obj) -> Obj:
    """
    Return type as is for immutable built-in types
    Use obj.copy() for built-in empty collections
    Use copy.deepcopy() for non-empty collections and unknown objects
    """

    obj_type = obj.__class__
    if obj_type in IMMUTABLE_NON_COLLECTIONS_TYPES:
        return obj  # fastest case: obj is immutable and not collection therefore will not be copied anyway
    try:
        if not obj and obj_type in BUILTIN_COLLECTIONS:
            # faster way for empty collections, no need to copy its members
            return obj if obj_type is tuple else obj.copy()  # type: ignore  # tuple doesn't have copy method
    except (TypeError, ValueError, RuntimeError):
        # do we really dare to catch ALL errors? Seems a bit risky
        pass

    return deepcopy(obj)  # slowest way when we actually might need a deepcopy


def is_valid_field(name: str) -> bool:
    return not name.startswith('_')


DUNDER_ATTRIBUTES = {
    '__annotations__',
    '__classcell__',
    '__doc__',
    '__module__',
    '__orig_bases__',
    '__orig_class__',
    '__qualname__',
}


def is_valid_private_name(name: str) -> bool:
    return not is_valid_field(name) and name not in DUNDER_ATTRIBUTES


_EMPTY = object()


def all_identical(left: Iterable[Any], right: Iterable[Any]) -> bool:
    """
    Check that the items of `left` are the same objects as those in `right`.

    >>> a, b = object(), object()
    >>> all_identical([a, b, a], [a, b, a])
    True
    >>> all_identical([a, b, [a]], [a, b, [a]])  # new list object, while "equal" is not "identical"
    False
    """
    for left_item, right_item in zip_longest(left, right, fillvalue=_EMPTY):
        if left_item is not right_item:
            return False
    return True


def assert_never(obj: NoReturn, msg: str) -> NoReturn:
    """
    Helper to make sure that we have covered all possible types.

    This is mostly useful for ``mypy``, docs:
    https://mypy.readthedocs.io/en/latest/literal_types.html#exhaustive-checks
    """
    raise TypeError(msg)


def get_unique_discriminator_alias(all_aliases: Collection[str], discriminator_key: str) -> str:
    """Validate that all aliases are the same and if that's the case return the alias"""
    unique_aliases = set(all_aliases)
    if len(unique_aliases) > 1:
        raise ConfigError(
            f'Aliases for discriminator {discriminator_key!r} must be the same (got {", ".join(sorted(all_aliases))})'
        )
    return unique_aliases.pop()


def get_discriminator_alias_and_values(tp: Any, discriminator_key: str) -> Tuple[str, Tuple[str, ...]]:
    """
    Get alias and all valid values in the `Literal` type of the discriminator field
    `tp` can be a `BaseModel` class or directly an `Annotated` `Union` of many.
    """
    is_root_model = getattr(tp, '__custom_root_type__', False)

    if get_origin(tp) is Annotated:
        tp = get_args(tp)[0]

    if hasattr(tp, '__pydantic_model__'):
        tp = tp.__pydantic_model__

    if origin_is_union(get_origin(tp)):
        alias, all_values = _get_union_alias_and_all_values(tp, discriminator_key)
        return alias, tuple(v for values in all_values for v in values)
    elif is_root_model:
        union_type = tp.__fields__[ROOT_KEY].type_
        alias, all_values = _get_union_alias_and_all_values(union_type, discriminator_key)

        if len(set(all_values)) > 1:
            raise ConfigError(
                f'Field {discriminator_key!r} is not the same for all submodels of {_repr.display_as_type(tp)!r}'
            )

        return alias, all_values[0]

    else:
        try:
            t_discriminator_type = tp.__fields__[discriminator_key].type_
        except AttributeError as e:
            raise TypeError(f'Type {tp.__name__!r} is not a valid `BaseModel` or `dataclass`') from e
        except KeyError as e:
            raise ConfigError(f'Model {tp.__name__!r} needs a discriminator field for key {discriminator_key!r}') from e

        if not is_literal_type(t_discriminator_type):
            raise ConfigError(f'Field {discriminator_key!r} of model {tp.__name__!r} needs to be a `Literal`')

        return tp.__fields__[discriminator_key].alias, all_literal_values(t_discriminator_type)


def _get_union_alias_and_all_values(
    union_type: Type[Any], discriminator_key: str
) -> Tuple[str, Tuple[Tuple[str, ...], ...]]:
    zipped_aliases_values = [get_discriminator_alias_and_values(t, discriminator_key) for t in get_args(union_type)]
    # unzip: [('alias_a',('v1', 'v2)), ('alias_b', ('v3',))] => [('alias_a', 'alias_b'), (('v1', 'v2'), ('v3',))]
    all_aliases, all_values = zip(*zipped_aliases_values)
    return get_unique_discriminator_alias(all_aliases, discriminator_key), all_values


KT = TypeVar('KT')
VT = TypeVar('VT')
if TYPE_CHECKING:
    # define like this to work with older python
    class LimitedDict(dict[KT, VT]):
        def __init__(self, size_limit: int = 1000):
            ...

else:

    class LimitedDict(dict):
        """
        Limit the size/length of a dict used for caching to avoid unlimited increase in memory usage.

        Since the dict is ordered, and we always remove elements from the beginning, this is effectively a FIFO cache.

        Annoying inheriting from `MutableMapping` breaks cython.
        """

        def __init__(self, size_limit: int = 1000):
            self.size_limit = size_limit
            super().__init__()

        def __setitem__(self, __key: Any, __value: Any) -> None:
            super().__setitem__(__key, __value)
            if len(self) > self.size_limit:
                excess = len(self) - self.size_limit + self.size_limit // 10
                to_remove = list(self.keys())[:excess]
                for key in to_remove:
                    del self[key]

        def __class_getitem__(cls, *args: Any) -> Any:
            # to avoid errors with 3.7
            pass
