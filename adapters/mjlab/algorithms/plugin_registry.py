"""Algorithm plugin registry loader with fail-closed semantics.

The registry (``registry.json`` next to this file) maps an algorithm name to
its plugin module, metadata, and runner-config variants.  Consumers:

- **Control plane** (no torch): ``load_registry`` / ``list_plugins`` /
  ``get_plugin_metadata`` / ``variant_entrypoints`` are pure JSON operations
  and validate the file fail-closed.
- **Training plane** (torch available): ``resolve_plugin`` imports the plugin
  module, instantiates the declared class, and protocol-checks it before
  returning; any drift between the JSON metadata and the class metadata is an
  error, not a fallback.
- **Runner binding**: ``bind_algorithm_to_runner_cfg`` writes the variant's
  ``class_name`` strings onto an ``RslRlOnPolicyRunnerCfg``-shaped object so a
  profile only needs ``algorithm_plugin: "<name>"`` instead of hardcoded
  per-family dicts.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from .base import (
  BUILD_METHODS,
  METADATA_FIELDS,
  REGISTRY_SCHEMA_VERSION,
  verify_plugin,
)

REGISTRY_FILE = Path(__file__).with_name("registry.json")

_REQUIRED_PLUGIN_KEYS = ("module", "plugin_class", "metadata")
_REQUIRED_VARIANT_KEYS = ("algorithm", "actor")


class PluginRegistryError(RuntimeError):
  """Raised for malformed registry data or unknown/misdeclared plugins."""


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
  """Load and validate ``registry.json`` (fail-closed on any violation)."""
  registry_path = Path(path) if path is not None else REGISTRY_FILE
  try:
    payload = json.loads(registry_path.read_text(encoding="utf-8-sig"))
  except (OSError, json.JSONDecodeError) as exc:
    raise PluginRegistryError(f"algorithm plugin registry unreadable: {exc}") from exc
  if not isinstance(payload, dict):
    raise PluginRegistryError("algorithm plugin registry must be a JSON object")
  if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
    raise PluginRegistryError(
      f"registry schema_version {payload.get('schema_version')!r} != expected "
      f"{REGISTRY_SCHEMA_VERSION!r}"
    )
  plugins = payload.get("plugins")
  if not isinstance(plugins, dict) or not plugins:
    raise PluginRegistryError("registry must declare a non-empty 'plugins' object")
  for name, entry in plugins.items():
    if not isinstance(entry, dict):
      raise PluginRegistryError(f"plugin {name!r} entry must be an object")
    for key in _REQUIRED_PLUGIN_KEYS:
      if not entry.get(key):
        raise PluginRegistryError(f"plugin {name!r} missing required key {key!r}")
    metadata = entry["metadata"]
    if not isinstance(metadata, dict):
      raise PluginRegistryError(f"plugin {name!r} metadata must be an object")
    if metadata.get("name") != name:
      raise PluginRegistryError(
        f"plugin {name!r} metadata.name mismatch: {metadata.get('name')!r}"
      )
    for field in METADATA_FIELDS:
      if not metadata.get(field):
        raise PluginRegistryError(
          f"plugin {name!r} metadata missing {field!r}"
        )
    if not isinstance(metadata.get("supported_obs_types"), list) or not metadata[
      "supported_obs_types"
    ]:
      raise PluginRegistryError(
        f"plugin {name!r} metadata.supported_obs_types must be a non-empty list"
      )
    variants = entry.get("variants")
    if not isinstance(variants, dict) or not variants:
      raise PluginRegistryError(f"plugin {name!r} must declare variants")
    for variant, binding in variants.items():
      if not isinstance(binding, dict):
        raise PluginRegistryError(
          f"plugin {name!r} variant {variant!r} must be an object"
        )
      for key in _REQUIRED_VARIANT_KEYS:
        if not binding.get(key):
          raise PluginRegistryError(
            f"plugin {name!r} variant {variant!r} missing {key!r}"
          )
  return payload


def list_plugins(path: str | Path | None = None) -> list[str]:
  """Sorted registry keys."""
  return sorted(load_registry(path)["plugins"])


def get_plugin_metadata(name: str, path: str | Path | None = None) -> dict[str, Any]:
  """Metadata for ``name``; unknown names fail closed."""
  plugins = load_registry(path)["plugins"]
  if name not in plugins:
    raise PluginRegistryError(
      f"unknown algorithm plugin {name!r}; available: {', '.join(sorted(plugins))}"
    )
  return dict(plugins[name]["metadata"])


def plugin_variants(name: str, path: str | Path | None = None) -> dict[str, dict]:
  """Variant -> class_name binding map for ``name``; unknown names fail closed."""
  plugins = load_registry(path)["plugins"]
  if name not in plugins:
    raise PluginRegistryError(
      f"unknown algorithm plugin {name!r}; available: {', '.join(sorted(plugins))}"
    )
  return {key: dict(value) for key, value in plugins[name]["variants"].items()}


def variant_entrypoints(
  name: str, variant: str = "base", path: str | Path | None = None
) -> dict[str, str]:
  """Runner-cfg class_name strings for one variant; unknown keys fail closed."""
  variants = plugin_variants(name, path)
  if variant not in variants:
    raise PluginRegistryError(
      f"unknown variant {variant!r} for algorithm plugin {name!r}; "
      f"available: {', '.join(sorted(variants))}"
    )
  binding = dict(variants[variant])
  # Keep only class-name fields the runner cfg understands.
  return {
    key: value
    for key, value in binding.items()
    if key in ("algorithm", "actor", "critic", "distribution")
  }


def resolve_plugin(name: str, path: str | Path | None = None) -> Any:
  """Import, instantiate, and protocol-check the plugin for ``name``.

  Requires the training stack (torch/rsl_rl) because plugin modules build nn
  modules; control-plane consumers should use ``get_plugin_metadata``.
  """
  plugins = load_registry(path)["plugins"]
  if name not in plugins:
    raise PluginRegistryError(
      f"unknown algorithm plugin {name!r}; available: {', '.join(sorted(plugins))}"
    )
  entry = plugins[name]
  module_path = entry["module"]
  plugin_class_name = entry["plugin_class"]
  try:
    module = importlib.import_module(module_path)
  except ImportError as exc:
    raise PluginRegistryError(
      f"algorithm plugin {name!r} module {module_path!r} failed to import "
      f"(training stack required): {exc}"
    ) from exc
  plugin_class = getattr(module, plugin_class_name, None)
  if plugin_class is None:
    raise PluginRegistryError(
      f"algorithm plugin {name!r}: {module_path} has no {plugin_class_name!r}"
    )
  plugin = plugin_class()
  violations = verify_plugin(plugin)
  if violations:
    raise PluginRegistryError(
      f"algorithm plugin {name!r} violates the plugin protocol: {violations}"
    )
  declared = entry["metadata"]
  for field in ("name", "upstream", "license"):
    if getattr(plugin, field) != declared[field]:
      raise PluginRegistryError(
        f"algorithm plugin {name!r} metadata drift: class {field}="
        f"{getattr(plugin, field)!r} vs registry {declared[field]!r}"
      )
  if tuple(plugin.supported_obs_types) != tuple(declared["supported_obs_types"]):
    raise PluginRegistryError(
      f"algorithm plugin {name!r} supported_obs_types drift: class="
      f"{tuple(plugin.supported_obs_types)!r} vs registry="
      f"{tuple(declared['supported_obs_types'])!r}"
    )
  return plugin


def bind_algorithm_to_runner_cfg(
  cfg: Any,
  name: str,
  variant: str = "base",
  path: str | Path | None = None,
) -> Any:
  """Write the variant's class_name strings onto a runner cfg object.

  Sets ``cfg.algorithm.class_name``, ``cfg.actor.class_name`` and (when the
  variant declares one) ``cfg.critic.class_name`` / the actor distribution
  class.  Returns ``cfg`` for chaining; unknown plugin/variant fail closed.
  """
  binding = variant_entrypoints(name, variant, path)
  cfg.algorithm.class_name = binding["algorithm"]
  cfg.actor.class_name = binding["actor"]
  if "critic" in binding:
    cfg.critic.class_name = binding["critic"]
  if "distribution" in binding and cfg.actor.distribution_cfg is not None:
    cfg.actor.distribution_cfg["class_name"] = binding["distribution"]
  return cfg


def apply_algorithm_plugin(
  cfg: Any,
  *,
  algorithm_plugin: str,
  variant: str | None = None,
  path: str | Path | None = None,
) -> dict[str, Any]:
  """把 profile 声明的 ``algorithm_plugin`` 绑到 runner cfg 上；返回留痕用的裁决。

  **profile 显式声明是唯一开关**：没有 ``algorithm_plugin`` 的 profile（历史上是绝大多数）
  走 mjlab 原生 dataclass cfg 路径，本函数不参与——"默认路径一行不碰"是硬约束。

  ``variant`` 省略时取 ``"base"``（注册表必须声明 base），注册表里没有 base 则取首字母序第一个；
  未知插件 / 未知变体由 :func:`variant_entrypoints` fail-closed。

  返回值形如 ``{"plugin": "him", "variant": "base", "algorithm": "<class_name>", ...}``，
  调用方把它写进 run 报告——"这次训练用的是哪个算法的哪套接线"必须可查，
  否则产物谱系在插件时代就断了。
  """

  name = str(algorithm_plugin).strip()
  variants = plugin_variants(name, path)
  chosen = str(variant).strip() if variant else ("base" if "base" in variants else sorted(variants)[0])
  binding = variant_entrypoints(name, chosen, path)
  bind_algorithm_to_runner_cfg(cfg, name, chosen, path)
  return {"plugin": name, "variant": chosen, **binding}


__all__ = [
  "BUILD_METHODS",
  "PluginRegistryError",
  "apply_algorithm_plugin",
  "bind_algorithm_to_runner_cfg",
  "get_plugin_metadata",
  "list_plugins",
  "load_registry",
  "plugin_variants",
  "resolve_plugin",
  "variant_entrypoints",
]
