# Frequenz Gridpool Library Release Notes

## Summary

<!-- Here goes a general summary of what this release is about -->

## Upgrading

<!-- Here goes notes on how to upgrade from previous versions, including deprecations and what they should be replaced with -->

## New Features

* `ComponentTypeConfig` has a new `units` field that keeps the inverter-to-component wiring explicit. Each entry pairs one inverter with the components wired to it, e.g. `1.ctype.battery.units = [{inverter = 201, component = [301, 302]}, {inverter = 202, component = [303]}]` in TOML. Before, consumers had to guess the pairing from the order of the flat `inverter` and `component` lists, which breaks as soon as the counts differ.

* When `units` is set and `inverter` or `component` is not, the missing list is filled in from the units. Explicitly given lists are checked against the units: a unit naming an unknown inverter or component is an error, and a component not wired to any inverter logs a warning.

* The `generate-config` CLI command writes `units` as an array of inline tables, both when printing and when patching with `--inplace`.

## Bug Fixes

<!-- Here goes notable bug fixes that are worth a special mention or explanation -->
