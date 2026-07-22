# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""Tests for the component graph generator."""

from unittest.mock import AsyncMock, MagicMock

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

from frequenz.gridpool import ComponentGraphConfig
from frequenz.gridpool._graph_generator import (
    ComponentGraphGenerator,
    battery_units,
)


def _mock_client() -> MagicMock:
    """Mock an Assets API client: grid 1 -> meter 2 -> solar inverter 4, + meter 3."""
    assets_client_mock = MagicMock(spec=AssetsApiClient)
    assets_client_mock.list_microgrid_electrical_components = AsyncMock(
        return_value=[
            GridConnectionPoint(
                id=ElectricalComponentId(1),
                microgrid_id=MicrogridId(10),
                rated_fuse_current=100,
            ),
            Meter(
                id=ElectricalComponentId(2),
                microgrid_id=MicrogridId(10),
            ),
            Meter(
                id=ElectricalComponentId(3),
                microgrid_id=MicrogridId(10),
            ),
            SolarInverter(
                id=ElectricalComponentId(4),
                microgrid_id=MicrogridId(10),
            ),
        ]
    )
    assets_client_mock.list_microgrid_electrical_component_connections = AsyncMock(
        return_value=[
            ComponentConnection(
                source=ElectricalComponentId(1),
                destination=ElectricalComponentId(2),
            ),
            ComponentConnection(
                source=ElectricalComponentId(1),
                destination=ElectricalComponentId(3),
            ),
            ComponentConnection(
                source=ElectricalComponentId(2),
                destination=ElectricalComponentId(4),
            ),
        ]
    )

    return assets_client_mock


async def test_formula_generation() -> None:
    """Test formula generation from component graph created from Assets API."""
    g = ComponentGraphGenerator(_mock_client())
    graph = await g.get_component_graph(MicrogridId(10))

    assert graph.grid_formula() == "COALESCE(#2, #4, 0.0) + #3"
    assert graph.pv_formula(None) == "COALESCE(#4, #2, 0.0)"


async def test_formula_generation_with_a_component_graph_config() -> None:
    """A component graph config reaches the generated formulas."""
    g = ComponentGraphGenerator(
        _mock_client(),
        ComponentGraphConfig(prefer_meters_in_component_formulas=True),
    )
    graph = await g.get_component_graph(MicrogridId(10))

    # Meter first, the opposite of the default order.
    assert graph.pv_formula(None) == "COALESCE(#2, #4, 0.0)"


def _mock_battery_client() -> MagicMock:
    """Mock an Assets API client with batteries behind two inverters.

    Topology: grid 1 -> meter 2 -> inverters 201 and 202; inverter 201
    drives batteries 301 and 302, inverter 202 drives battery 303.
    """
    assets_client_mock = MagicMock(spec=AssetsApiClient)
    assets_client_mock.list_microgrid_electrical_components = AsyncMock(
        return_value=[
            GridConnectionPoint(
                id=ElectricalComponentId(1),
                microgrid_id=MicrogridId(10),
                rated_fuse_current=100,
            ),
            Meter(id=ElectricalComponentId(2), microgrid_id=MicrogridId(10)),
            BatteryInverter(
                id=ElectricalComponentId(202), microgrid_id=MicrogridId(10)
            ),
            BatteryInverter(
                id=ElectricalComponentId(201), microgrid_id=MicrogridId(10)
            ),
            LiIonBattery(id=ElectricalComponentId(301), microgrid_id=MicrogridId(10)),
            LiIonBattery(id=ElectricalComponentId(302), microgrid_id=MicrogridId(10)),
            LiIonBattery(id=ElectricalComponentId(303), microgrid_id=MicrogridId(10)),
        ]
    )
    assets_client_mock.list_microgrid_electrical_component_connections = AsyncMock(
        return_value=[
            ComponentConnection(
                source=ElectricalComponentId(1), destination=ElectricalComponentId(2)
            ),
            ComponentConnection(
                source=ElectricalComponentId(2), destination=ElectricalComponentId(201)
            ),
            ComponentConnection(
                source=ElectricalComponentId(2), destination=ElectricalComponentId(202)
            ),
            ComponentConnection(
                source=ElectricalComponentId(201),
                destination=ElectricalComponentId(301),
            ),
            ComponentConnection(
                source=ElectricalComponentId(201),
                destination=ElectricalComponentId(302),
            ),
            ComponentConnection(
                source=ElectricalComponentId(202),
                destination=ElectricalComponentId(303),
            ),
        ]
    )

    return assets_client_mock


async def test_battery_units() -> None:
    """Each battery inverter is paired with exactly the batteries wired to it."""
    g = ComponentGraphGenerator(_mock_battery_client())
    graph = await g.get_component_graph(MicrogridId(10))

    # Sorted by inverter ID even though 202 was listed before 201.
    assert battery_units(graph) == {201: [301, 302], 202: [303]}
