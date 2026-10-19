"""Loading and scaling sprite and artwork images."""

from collections import OrderedDict

import pygame

from pokedex.paths import DataPaths


class ImageCache:
    """Scaled images keyed by (stored path, size), least recently used dropped first.

    The limit keeps memory bounded on a Pi when browsing all 1,025 Pokémon.
    """

    def __init__(self, paths: DataPaths, max_items: int = 96) -> None:
        self._paths = paths
        self._max_items = max_items
        self._cache: OrderedDict[tuple[str, int], pygame.Surface | None] = OrderedDict()

    def get(self, stored_path: str | None, size: int) -> pygame.Surface | None:
        """The image scaled to fit a size x size box, or None if it is missing."""
        if not stored_path:
            return None
        key = (stored_path, size)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        image = self._load(stored_path, size)
        self._cache[key] = image
        if len(self._cache) > self._max_items:
            self._cache.popitem(last=False)
        return image

    def _load(self, stored_path: str, size: int) -> pygame.Surface | None:
        try:
            image = pygame.image.load(self._paths.resolve(stored_path)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            return None
        return scale_to_fit(image, size)


def scale_to_fit(image: pygame.Surface, size: int) -> pygame.Surface:
    width, height = image.get_size()
    factor = size / max(width, height)
    if factor >= 2:
        # Enlarge pixel sprites by a whole number so they stay crisp.
        whole = int(factor)
        return pygame.transform.scale(image, (width * whole, height * whole))
    return pygame.transform.smoothscale(
        image, (max(1, round(width * factor)), max(1, round(height * factor)))
    )
