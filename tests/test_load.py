# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""Tests for loading microgrid configs from the Assets API."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from frequenz.client.assets import AssetsApiClient
from frequenz.client.assets.electrical_component import (
    BatteryInverter,
    ComponentConnection,
    GridConnectionPoint,
    LiIonBattery,
    Meter,
    SolarInverter,
)
from frequenz.client.common.microgrid import MicrogridId
from frequenz.client.common.microgrid.electrical_components import ElectricalComponentId

from frequenz.gridpool import ComponentGraphConfig, ComponentUnitConfig
from frequenz.gridpool._graph_generator import (
    ComponentGraphGenerator,
    MicrogridComponentGraph,
)
from frequenz.gridpool.config.load import (
    _derive_component_configs,
    load_configs,
    load_configs_from_api,
)


def _mock_client() -> MagicMock:
    """Mock an Assets API client for one microgrid: grid -> meter -> PV, + a meter."""
    client = MagicMock(spec=AssetsApiClient)
    client.get_microgrid = AsyncMock(return_value=MagicMock(location=None))
    client.list_microgrid_electrical_components = AsyncMock(
        return_value=[
            GridConnectionPoint(
                id=ElectricalComponentId(1),
                microgrid_id=MicrogridId(10),
                rated_fuse_current=100,
            ),
            Meter(id=ElectricalComponentId(2), microgrid_id=MicrogridId(10)),
            Meter(id=ElectricalComponentId(3), microgrid_id=MicrogridId(10)),
            SolarInverter(id=ElectricalComponentId(4), microgrid_id=MicrogridId(10)),
        ]
    )
    client.list_microgrid_electrical_component_connections = AsyncMock(
        return_value=[
            ComponentConnection(
                source=ElectricalComponentId(1), destination=ElectricalComponentId(2)
            ),
            ComponentConnection(
                source=ElectricalComponentId(1), destination=ElectricalComponentId(3)
            ),
            ComponentConnection(
                source=ElectricalComponentId(2), destination=ElectricalComponentId(4)
            ),
        ]
    )
    return client


async def _build_graph(client: MagicMock) -> MicrogridComponentGraph:
    return await ComponentGraphGenerator(client).get_component_graph(MicrogridId(10))


async def test_load_configs_from_api_derives_formulas_and_ids() -> None:
    """A config loaded from the API gets both formulas and component IDs."""
    configs = await load_configs_from_api(_mock_client(), [10])

    cfg = configs["10"]
    assert cfg.ctype["pv"].formula == {"AC_POWER_ACTIVE": "COALESCE(#4, #2, 0.0)"}
    assert cfg.ctype["pv"].inverter == [4]
    assert cfg.ctype["pv"].meter == [2]
    assert cfg.ctype["grid"].meter == [2, 3]
    # Component types absent from the microgrid are not created.
    assert set(cfg.ctype) == {"grid", "consumption", "pv"}


async def test_load_configs_from_api_honours_the_component_graph_config() -> None:
    """A component graph config reaches the derived formulas."""
    configs = await load_configs_from_api(
        _mock_client(),
        [10],
        component_graph_config=ComponentGraphConfig(
            prefer_meters_in_component_formulas=True
        ),
    )

    # Meter first, the opposite of the default order asserted above.
    ctype = configs["10"].ctype
    assert ctype["pv"].formula == {"AC_POWER_ACTIVE": "COALESCE(#2, #4, 0.0)"}


async def test_load_configs_forwards_the_component_graph_config() -> None:
    """`load_configs` passes its component graph config down to the API layer."""
    configs = await load_configs(
        assets_client=_mock_client(),
        microgrid_ids=[10],
        component_graph_config=ComponentGraphConfig(
            prefer_meters_in_component_formulas=True
        ),
    )

    assert configs["10"].ctype["pv"].formula == {
        "AC_POWER_ACTIVE": "COALESCE(#2, #4, 0.0)"
    }


async def test_load_configs_rejects_a_component_graph_config_without_a_client() -> None:
    """A component graph config is only meaningful with an Assets API client."""
    with pytest.raises(ValueError, match="requires an assets_client"):
        await load_configs(
            default_files=[],
            component_graph_config=ComponentGraphConfig(),
        )


async def test_load_configs_from_api_keeps_metadata_when_graph_fails() -> None:
    """A graph-derivation failure still yields a metadata-only config."""
    client = _mock_client()
    client.list_microgrid_electrical_components = AsyncMock(
        side_effect=RuntimeError("graph unavailable")
    )

    configs = await load_configs_from_api(client, [10])

    cfg = configs["10"]
    assert cfg.meta.microgrid_id == 10
    assert cfg.ctype == {}


async def test_derive_component_configs_builds_formulas_and_ids() -> None:
    """The builder derives formulas and IDs and omits types with neither."""
    graph = await _build_graph(_mock_client())

    configs = _derive_component_configs(graph)

    assert configs["pv"].formula == {"AC_POWER_ACTIVE": "COALESCE(#4, #2, 0.0)"}
    assert configs["pv"].inverter == [4]
    assert configs["pv"].meter == [2]
    assert configs["grid"].meter == [2, 3]
    assert set(configs) == {"grid", "consumption", "pv"}


def _mock_battery_client() -> MagicMock:
    """Mock an Assets API client: grid 1 -> meter 2 -> inverters 201/202 -> batteries."""
    client = MagicMock(spec=AssetsApiClient)
    client.get_microgrid = AsyncMock(return_value=MagicMock(location=None))
    mid = MicrogridId(10)
    eid = ElectricalComponentId
    client.list_microgrid_electrical_components = AsyncMock(
        return_value=[
            GridConnectionPoint(id=eid(1), microgrid_id=mid, rated_fuse_current=100),
            Meter(id=eid(2), microgrid_id=mid),
            BatteryInverter(id=eid(201), microgrid_id=mid),
            BatteryInverter(id=eid(202), microgrid_id=mid),
            LiIonBattery(id=eid(301), microgrid_id=mid),
            LiIonBattery(id=eid(302), microgrid_id=mid),
            LiIonBattery(id=eid(303), microgrid_id=mid),
        ]
    )
    client.list_microgrid_electrical_component_connections = AsyncMock(
        return_value=[
            ComponentConnection(source=eid(1), destination=eid(2)),
            ComponentConnection(source=eid(2), destination=eid(201)),
            ComponentConnection(source=eid(2), destination=eid(202)),
            ComponentConnection(source=eid(201), destination=eid(301)),
            ComponentConnection(source=eid(201), destination=eid(302)),
            ComponentConnection(source=eid(202), destination=eid(303)),
        ]
    )
    return client


async def test_load_configs_from_api_pairs_batteries_with_their_inverter() -> None:
    """A config loaded from the API carries the inverter-to-battery wiring."""
    configs = await load_configs_from_api(_mock_battery_client(), [10])

    battery = configs["10"].ctype["battery"]
    assert battery.units == [
        ComponentUnitConfig(inverter=201, component=[301, 302]),
        ComponentUnitConfig(inverter=202, component=[303]),
    ]
    # The flat lists stay consistent with the units.
    assert battery.inverter == [201, 202]
    assert battery.component == [301, 302, 303]
