from __future__ import annotations as _annotations

import json
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, ForwardRef, Optional, Tuple, Type, Union

from typing_extensions import Literal, Protocol, TypedDict

from ._internal.typing_extra import AnyArgTCallable, AnyCallable
from .utils import GetterDict

if TYPE_CHECKING:
    from typing import overload

    from .fields import ModelField
    from .main import BaseModel

    ConfigType = Type['BaseConfig']

    class SchemaExtraCallable(Protocol):
        @overload
        def __call__(self, schema: Dict[str, Any]) -> None:
            pass

        @overload
        def __call__(self, schema: Dict[str, Any], model_class: Type[BaseModel]) -> None:
            pass

else:
    SchemaExtraCallable = Callable[..., None]

__all__ = 'BaseConfig', 'ConfigDict', 'get_config', 'Extra', 'build_config', 'inherit_config', 'prepare_config'


class Extra(str, Enum):
    allow = 'allow'
    ignore = 'ignore'
    forbid = 'forbid'


class ConfigDict(TypedDict, total=False):
    title: Optional[str]
    anystr_lower: bool
    anystr_strip_whitespace: bool
    min_anystr_length: int
    max_anystr_length: Optional[int]
    validate_all: bool
    extra: Extra
    allow_mutation: bool
    frozen: bool
    allow_population_by_field_name: bool
    use_enum_values: bool
    fields: Dict[str, Union[str, Dict[str, str]]]
    validate_assignment: bool
    error_msg_templates: Dict[str, str]
    arbitrary_types_allowed: bool
    orm_mode: bool
    getter_dict: Type[GetterDict]
    alias_generator: Optional[Callable[[str], str]]
    keep_untouched: Tuple[type, ...]
    schema_extra: Union[Dict[str, object], 'SchemaExtraCallable']
    json_loads: Callable[[str], object]
    json_dumps: AnyArgTCallable[str]
    json_encoders: Dict[Type[object], AnyCallable]
    underscore_attrs_are_private: bool
    allow_inf_nan: bool
    copy_on_model_validation: Literal['none', 'deep', 'shallow']
    post_init_call: Literal['before_validation', 'after_validation']


class BaseConfig:
    title: Optional[str] = None
    anystr_lower: bool = False
    anystr_upper: bool = False
    anystr_strip_whitespace: bool = False
    min_anystr_length: int = 0
    max_anystr_length: Optional[int] = None
    validate_all: bool = False
    extra: Extra = Extra.ignore
    allow_mutation: bool = True
    frozen: bool = False
    allow_population_by_field_name: bool = False
    use_enum_values: bool = False
    fields: Dict[str, Union[str, Dict[str, str]]] = {}
    validate_assignment: bool = False
    error_msg_templates: Dict[str, str] = {}
    arbitrary_types_allowed: bool = False
    orm_mode: bool = False
    getter_dict: Type[GetterDict] = GetterDict
    alias_generator: Optional[Callable[[str], str]] = None
    keep_untouched: Tuple[type, ...] = ()
    schema_extra: Union[Dict[str, Any], 'SchemaExtraCallable'] = {}
    json_loads: Callable[[str], Any] = json.loads
    json_dumps: Callable[..., str] = json.dumps
    json_encoders: Dict[Union[Type[Any], str, ForwardRef], AnyCallable] = {}
    underscore_attrs_are_private: bool = False
    allow_inf_nan: bool = True

    # whether inherited models as fields should be reconstructed as base model,
    # and whether such a copy should be shallow or deep
    copy_on_model_validation: Literal['none', 'deep', 'shallow'] = 'shallow'

    # whether `Union` should check all allowed types before even trying to coerce
    smart_union: bool = False
    # whether dataclass `__post_init__` should be run before or after validation
    post_init_call: Literal['before_validation', 'after_validation'] = 'before_validation'

    @classmethod
    def get_field_info(cls, name: str) -> Dict[str, Any]:
        """
        Get properties of FieldInfo from the `fields` property of the config class.
        """

        fields_value = cls.fields.get(name)

        if isinstance(fields_value, str):
            field_info: Dict[str, Any] = {'alias': fields_value}
        elif isinstance(fields_value, dict):
            field_info = fields_value
        else:
            field_info = {}

        if 'alias' in field_info:
            field_info.setdefault('alias_priority', 2)

        if field_info.get('alias_priority', 0) <= 1 and cls.alias_generator:
            alias = cls.alias_generator(name)
            if not isinstance(alias, str):
                raise TypeError(f'Config.alias_generator must return str, not {alias.__class__}')
            field_info.update(alias=alias, alias_priority=1)
        return field_info

    @classmethod
    def prepare_field(cls, field: 'ModelField') -> None:
        """
        Optional hook to check or modify fields during model creation.
        """
        pass


def get_config(config: Union[ConfigDict, Type[object], None]) -> Type[BaseConfig]:
    if config is None:
        return BaseConfig

    else:
        config_dict = (
            config
            if isinstance(config, dict)
            else {k: getattr(config, k) for k in dir(config) if not k.startswith('__')}
        )

        class Config(BaseConfig):
            ...

        for k, v in config_dict.items():
            setattr(Config, k, v)
        return Config


def inherit_config(self_config: 'ConfigType', parent_config: 'ConfigType', **namespace: Any) -> 'ConfigType':
    # TODO remove
    if not self_config:
        base_classes: Tuple['ConfigType', ...] = (parent_config,)
    elif self_config == parent_config:
        base_classes = (self_config,)
    else:
        base_classes = self_config, parent_config

    namespace['json_encoders'] = {
        **getattr(parent_config, 'json_encoders', {}),
        **getattr(self_config, 'json_encoders', {}),
        **namespace.get('json_encoders', {}),
    }

    return type('Config', base_classes, namespace)


def build_config(
    cls_name: str, bases: tuple[type[Any], ...], namespace: dict[str, Any], kwargs: dict[str, Any]
) -> tuple[type[BaseConfig], type[BaseConfig] | None]:
    """
    TODO update once we're sure what this does.

    Note: merging json_encoders is not currently implemented
    """
    config_kwargs = {k: v for k, v in kwargs.items() if not k.startswith('_')}
    config_from_namespace = namespace.get('Config')

    config_bases = []
    for base in bases:
        config = getattr(base, 'Config', None)
        if config:
            config_bases.append(config)

    if len(config_bases) == 1 and not any([config_kwargs, config_from_namespace]):
        return BaseConfig, None

    if config_from_namespace:
        config_bases = [config_from_namespace] + config_bases

    combined_config: type[BaseConfig] = type('CombinedConfig', tuple(config_bases), config_kwargs)
    prepare_config(combined_config, cls_name)

    if config_from_namespace and config_kwargs:
        # we want to override `Config` so future inheritance includes config_kwargs
        new_model_config: type[BaseConfig] = type('ConfigWithKwargs', (config_from_namespace,), config_kwargs)
        return combined_config, new_model_config
    else:
        # we want to use CombinedConfig for `__config__`, but we
        return combined_config, None


def prepare_config(config: Type[BaseConfig], cls_name: str) -> None:
    if not isinstance(config.extra, Extra):
        try:
            config.extra = Extra(config.extra)
        except ValueError:
            raise ValueError(f'"{cls_name}": {config.extra} is not a valid value for "extra"')
