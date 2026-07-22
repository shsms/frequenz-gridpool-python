# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""Data model for microgrid configurations."""

import logging
import re
import tomllib
from copy import deepcopy
from dataclasses import field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, Self, Type, cast, get_args

from marshmallow import Schema
from marshmallow_dataclass import dataclass

_logger = logging.getLogger(__name__)


ComponentType = Literal["grid", "pv", "battery", "consumption", "chp", "ev"]
"""Valid component types."""

ComponentCategory = Literal["meter", "inverter", "component"]
"""Valid component categories."""


@dataclass
class ComponentUnitConfig:
    """One inverter and the components wired to it.

    A unit keeps the wiring explicit, so consumers can pair an inverter
    with its components without guessing from the order of the flat ID
    lists in `ComponentTypeConfig`.
    """

    inverter: int
    """ID of the inverter of this unit."""

    component: list[int] = field(default_factory=list)
    """IDs of the components wired to this inverter, e.g. battery packs.

    Empty if the inverter has no components connected to it.
    """


@dataclass
class ComponentTypeConfig:
    """Configuration of a microgrid component type."""

    meter: list[int] | None = None
    """List of meter IDs for this component."""

    inverter: list[int] | None = None
    """List of inverter IDs for this component."""

    component: list[int] | None = None
    """List of component IDs for this component."""

    formula: dict[str, str] | None = None
    """Formula to calculate the power of this component."""

    units: list[ComponentUnitConfig] | None = None
    """Inverter-to-component wiring, one entry per inverter.

    This is the authoritative pairing: consumers that need to know which
    components belong to which inverter must read it from here, not guess
    it from the order of the `inverter` and `component` lists.

    When `units` is set and `inverter` or `component` is not, the missing
    list is filled in from the units.
    """

    def __post_init__(self) -> None:
        """Set the default formula and reconcile `units` with the ID lists."""
        self.formula = self.formula or {}
        if "AC_ACTIVE_POWER" in self.formula:
            _logger.warning(
                "ComponentTypeConfig: 'AC_ACTIVE_POWER' formula is deprecated, "
                "please use 'AC_POWER_ACTIVE' instead."
            )
        if self.units is not None:
            self._reconcile_units()

    def _reconcile_units(self) -> None:
        """Fill the `inverter`/`component` lists from `units`, or check them.

        Raises:
            ValueError: If a unit's inverter or component is missing from an
                explicitly given `inverter` or `component` list.
        """
        assert self.units is not None
        unit_inverters = [u.inverter for u in self.units]
        unit_components = [c for u in self.units for c in u.component]

        if self.inverter is None:
            self.inverter = unit_inverters
        elif missing := set(unit_inverters) - set(self.inverter):
            raise ValueError(
                f"units name inverters {sorted(missing)} that are not in the "
                f"inverter list {self.inverter}"
            )

        if self.component is None:
            self.component = unit_components
        elif missing := set(unit_components) - set(self.component):
            raise ValueError(
                f"units name components {sorted(missing)} that are not in the "
                f"component list {self.component}"
            )
        elif unpaired := set(self.component) - set(unit_components):
            _logger.warning(
                "ComponentTypeConfig: components %s are not wired to any "
                "inverter in units",
                sorted(unpaired),
            )

    def cids(self, metric: str = "") -> list[int]:
        """Get component IDs for this component.

        By default, the meter IDs are returned if available, otherwise the inverter IDs.
        For components without meters or inverters, the component IDs are returned.

        If a metric is provided, the component IDs are extracted from the formula.

        Args:
            metric: Metric name of the formula.

        Returns:
            List of component IDs for this component.

        Raises:
            ValueError: If the metric is not supported or improperly set.
        """
        if metric:
            if not isinstance(self.formula, dict):
                raise ValueError("Formula must be a dictionary.")
            formula = self.formula.get(metric)
            if not formula:
                raise ValueError(f"{metric} does not have a formula")
            # Extract component IDs from the formula which are given as e.g. #123
            pattern = r"#(\d+)"
            return [int(e) for e in re.findall(pattern, self.formula[metric])]

        return self._default_cids()

    def _default_cids(self) -> list[int]:
        """Get the default component IDs for this component.

        If available, the meter IDs are returned, otherwise the inverter IDs.
        For components without meters or inverters, the component IDs are returned.

        Returns:
            List of component IDs for this component.

        Raises:
            ValueError: If no IDs are available.
        """
        if self.meter:
            return self.meter
        if self.inverter:
            return self.inverter
        if self.component:
            return self.component

        raise ValueError("No IDs available")

    @classmethod
    def is_valid_type(cls, ctype: str) -> bool:
        """Check if `ctype` is a valid enum value."""
        return ctype in get_args(ComponentType)


@dataclass(frozen=True)
class PVConfig:
    """Configuration of a PV system in a microgrid."""

    start_time: datetime | None = None
    """Start time of the PV system installation."""

    end_time: datetime | None = None
    """End time of the PV system installation."""

    peak_power: float | None = None
    """Peak power of the PV system in Watt."""

    rated_power: float | None = None
    """Rated power of the inverters in Watt."""

    curtailable: bool | None = None
    """Flag to indicate if PV system can be curtailed."""


@dataclass(frozen=True)
class WindConfig:
    # pylint: disable=too-many-instance-attributes
    """Configuration of a wind turbine in a microgrid."""

    start_time: datetime | None = None
    """Start time of the wind turbine installation."""

    end_time: datetime | None = None
    """End time of the wind turbine installation."""

    turbine_model: str | None = None
    """Model name of the wind turbine."""

    rated_power: float | None = None
    """Rated power of the wind turbine in Watt."""

    turbine_height: float | None = None
    """Height of the wind turbine in meters."""

    number_of_turbines: int = 1
    """Number of wind turbines."""

    hellmann_exponent: float | None = None
    """Hellmann exponent for wind speed extrapolation. See: https://w.wiki/FMw9"""

    longitude: float | None = None
    """Geographic longitude of the wind turbine."""

    latitude: float | None = None
    """Geographic latitude of the wind turbine."""


@dataclass(frozen=True)
class BatteryConfig:
    """Configuration of a battery in a microgrid."""

    start_time: datetime | None = None
    """Start time of the battery installation."""

    end_time: datetime | None = None
    """End time of the battery installation."""

    capacity: float | None = None
    """Capacity of the battery in Wh."""


# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class Metadata:
    """Metadata for a microgrid."""

    microgrid_id: int
    """ID of the microgrid."""

    name: str | None = None
    """Name of the microgrid."""

    enterprise_id: int | None = None
    """Enterprise ID of the microgrid."""

    gid: int | None = None
    """Gridpool ID of the microgrid."""

    delivery_area: str | None = None
    """Delivery area of the microgrid."""

    latitude: float | None = None
    """Geographic latitude of the microgrid."""

    longitude: float | None = None
    """Geographic longitude of the microgrid."""

    altitude: float | None = None
    """Geographic altitude of the microgrid."""

    start_time: datetime | None = None
    """Start time of the microgrid operation."""

    end_time: datetime | None = None
    """End time of the microgrid operation."""


@dataclass
class MicrogridConfig:
    """Configuration of a microgrid."""

    meta: Metadata
    """Metadata of the microgrid."""

    pv: dict[str, PVConfig] | None = None
    """Configuration of the PV system."""

    wind: dict[str, WindConfig] | None = None
    """Configuration of the wind turbines."""

    battery: dict[str, BatteryConfig] | None = None
    """Configuration of the batteries."""

    ctype: dict[str, ComponentTypeConfig] = field(default_factory=dict)
    """Mapping of component category types to ac power component config."""

    def component_types(self) -> list[str]:
        """Get a list of all component types in the configuration."""
        return list(self.ctype.keys())

    def component_type_ids(
        self,
        component_type: str,
        component_category: str | None = None,
        metric: str = "",
    ) -> list[int]:
        """Get a list of all component IDs for a component type.

        Args:
            component_type: Component type to be aggregated.
            component_category: Specific category of component IDs to retrieve
                (e.g., "meter", "inverter", or "component"). If not provided,
                the default logic is used.
            metric: Metric name of the formula if CIDs should be extracted from the formula.

        Returns:
            List of component IDs for this component type.

        Raises:
            ValueError: If the component type is unknown.
            KeyError: If `component_category` is invalid.
        """
        cfg = self.ctype.get(component_type)
        if not cfg:
            raise ValueError(f"{component_type} not found in config.")

        if component_category:
            valid_categories = get_args(ComponentCategory)
            if component_category not in valid_categories:
                raise KeyError(
                    f"Invalid component category: {component_category}. "
                    f"Valid categories are {valid_categories}"
                )
            category_ids = cast(list[int], getattr(cfg, component_category, []))
            return category_ids

        return cfg.cids(metric)

    def formula(self, component_type: str, metric: str) -> str:
        """Get the formula for a component type.

        Args:
            component_type: Component type to be aggregated.
            metric: Metric to be aggregated.

        Returns:
            Formula to be used for this aggregated component as string.

        Raises:
            ValueError: If the component type is unknown or formula is missing.
        """
        cfg = self.ctype.get(component_type)
        if not cfg:
            raise ValueError(f"{component_type} not found in config.")
        if cfg.formula is None:
            raise ValueError(f"No formula set for {component_type}")
        formula = cfg.formula.get(metric)
        if not formula:
            raise ValueError(f"{component_type} is missing formula for {metric}")

        return formula

    Schema: ClassVar[Type[Schema]] = Schema

    @classmethod
    def _load_table_entries(cls, data: dict[str, Any]) -> dict[str, Self]:
        """Load microgrid configurations from table entries.

        Args:
            data: The loaded TOML data.

        Returns:
            A dict mapping microgrid IDs to MicrogridConfig instances.

        Raises:
            ValueError: If top-level keys are not numeric microgrid IDs
                or if there is a microgrid ID mismatch.
            TypeError: If microgrid data is not a dict.
        """
        if not all(str(k).isdigit() for k in data.keys()):
            raise ValueError("All top-level keys must be numeric microgrid IDs.")

        mgrids = {}
        for mid, entry in data.items():
            if not mid.isdigit():
                raise ValueError(
                    f"Table reader: Microgrid ID key must be numeric, got {mid}"
                )
            if not isinstance(entry, dict):
                raise TypeError("Table reader: Each microgrid entry must be a dict")

            mgrid = cls.Schema().load(entry)
            if mgrid.meta is None or mgrid.meta.microgrid_id is None:
                raise ValueError(
                    "Table reader: Each microgrid entry must have a meta.microgrid_id"
                )
            if int(mgrid.meta.microgrid_id) != int(mid):
                raise ValueError(
                    f"Table reader: Microgrid ID mismatch: key {mid} != {mgrid.meta.microgrid_id}"
                )

            mgrids[mid] = mgrid

        return mgrids

    @classmethod
    def load_from_file(cls, config_path: Path) -> dict[str, Self]:
        """
        Load and validate configuration settings from a TOML file.

        Args:
            config_path: the path to the TOML configuration file.

        Returns:
            A dict mapping microgrid IDs to MicrogridConfig instances.
        """
        with config_path.open("rb") as f:
            data = tomllib.load(f)

        assert isinstance(data, dict)

        return cls._load_table_entries(data)


def merge_microgrid_configs(
    base: MicrogridConfig,
    override: MicrogridConfig,
) -> MicrogridConfig:
    """Merge two `MicrogridConfig` objects.

    The *override* config takes precedence over *base*.  Nested dictionaries
    are merged recursively.  If a field in *override* is `None` the value
    from *base* is retained, so partial overrides never nullify existing data.

    Args:
        base: The base MicrogridConfig.
        override: The overriding MicrogridConfig.

    Returns:
        A new MicrogridConfig representing the merged result.
    """
    schema = MicrogridConfig.Schema()
    base_dict = schema.dump(base)
    override_dict = schema.dump(override)

    def _deep_merge(a: dict[Any, Any], b: dict[Any, Any]) -> dict[Any, Any]:
        result = deepcopy(a)
        for k, v in b.items():
            if v is None:
                continue
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    merged = schema.load(_deep_merge(base_dict, override_dict))
    assert isinstance(merged, MicrogridConfig)
    return merged


def merge_config_maps(
    base: dict[str, MicrogridConfig],
    override: dict[str, MicrogridConfig],
) -> dict[str, MicrogridConfig]:
    """Merge two dictionaries of `MicrogridConfig` objects.

    For microgrid IDs present in both maps the configs are merged via
    `merge_microgrid_configs`.  IDs that exist only in one map are
    included unchanged.

    Args:
        base: The base dictionary of MicrogridConfig objects.
        override: The overriding dictionary of MicrogridConfig objects.

    Returns:
        A new dictionary representing the merged result.
    """
    merged = dict(base)
    for mid, cfg in override.items():
        if mid in merged:
            merged[mid] = merge_microgrid_configs(merged[mid], cfg)
        else:
            merged[mid] = cfg
    return merged
