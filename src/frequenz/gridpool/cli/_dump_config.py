# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""Serialize microgrid configurations to dotted-key TOML.

Renders a `{microgrid_id: MicrogridConfig}` mapping as dotted-key TOML, e.g.:

    115.meta.microgrid_id = 115
    115.meta.name = "Demo Grid"
    115.meta.latitude = 52.52

This is the inverse of `load_configs_from_files`. Value rendering (quoting,
escaping, key-quoting, list/number/datetime formatting) is delegated to
`tomlkit`; only the flattening to dotted keys and the dropping of empty/`None`
fields are done here, since TOML has no null and `tomlkit` rejects it.
"""

from typing import Any

import tomlkit
from tomlkit.items import Integer, Trivia

from frequenz.gridpool import MicrogridConfig


def _is_empty(value: Any) -> bool:
    """Whether a dumped value should be omitted from the output."""
    return value is None or value == {} or value == []


def _format_value(value: Any) -> Any:
    """Render whole-number floats and ints as underscore-grouped ints, e.g. `1_736_680`.

    Args:
        value: The value about to be written to the TOML document.

    Returns:
        The formatted value, or `value` itself if it is not a whole number.
    """
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and not isinstance(value, bool):
        # tomlkit.integer() just does int(raw), dropping underscores; build
        # the Integer item directly instead.
        return Integer(value, Trivia(), f"{value:_d}")
    if isinstance(value, list) and any(isinstance(entry, dict) for entry in value):
        # tomlkit turns a plain list of dicts into an array-of-tables, which
        # cannot sit on a dotted key; build an array of inline tables instead.
        array = tomlkit.array()
        for entry in value:
            table = tomlkit.inline_table()
            for key, entry_value in entry.items():
                if not _is_empty(entry_value):
                    table[key] = entry_value
            array.append(table)
        return array
    return value


def _iter_leaves(
    prefix: list[str], data: dict[str, Any]
) -> list[tuple[list[str], Any]]:
    """Flatten a nested dict into `(key_path, value)` pairs, dropping empties.

    Args:
        prefix: The key-path prefix accumulated so far.
        data: The nested mapping to flatten.

    Returns:
        A list of `(key_path, leaf_value)` pairs, where `key_path` is the list
        of nested keys leading to a non-empty scalar or list value.
    """
    leaves: list[tuple[list[str], Any]] = []
    for key, value in data.items():
        if _is_empty(value):
            continue
        path = prefix + [key]
        if isinstance(value, dict):
            leaves.extend(_iter_leaves(path, value))
        else:
            leaves.append((path, value))
    return leaves


def dump_map(configs: dict[str, MicrogridConfig]) -> str:
    """Serialize a mapping of microgrid configs to dotted-key TOML.

    Args:
        configs: Mapping from microgrid ID (as string) to `MicrogridConfig`.

    Returns:
        The TOML representation as a string, with one blank line between
        microgrids and entries sorted by numeric microgrid ID.
    """
    schema = MicrogridConfig.Schema()
    doc = tomlkit.document()
    for mid in sorted(configs, key=int):
        dumped = schema.dump(configs[mid])
        assert isinstance(dumped, dict)
        leaves = _iter_leaves([mid], dumped)
        if not leaves:
            continue
        if doc.body:
            doc.add(tomlkit.nl())
        for path, value in leaves:
            doc.append(tomlkit.key(path), _format_value(value))
    return tomlkit.dumps(doc)
