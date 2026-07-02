from __future__ import annotations

from typing import Callable, Dict, List, Optional, Type


class GenoscribePlugin:
    """Base class for future domain-specific extensions."""

    name: str = "plugin"

    def register_tools(self) -> None:
        raise NotImplementedError("Plugins must implement register_tools.")


class PluginRegistry:
    """Simple registry to keep track of installed plugins."""

    def __init__(self) -> None:
        self._plugins: Dict[str, GenoscribePlugin] = {}

    def register(self, plugin: GenoscribePlugin) -> None:
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Optional[GenoscribePlugin]:
        return self._plugins.get(name)

    def all_plugins(self) -> List[GenoscribePlugin]:
        return list(self._plugins.values())
