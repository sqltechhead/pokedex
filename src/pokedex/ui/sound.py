"""Playing an entry's audio: the Pokémon's cry, then the Pokédex reading the entry."""

from contextlib import suppress

import pygame

from pokedex.models import Pokemon
from pokedex.paths import DataPaths
from pokedex.ui.settings import Settings

FINISHED = pygame.event.custom_type()
"""Posted when the entry channel stops; the app passes it to EntryAudio.handle_event."""


class EntryAudio:
    """Plays one entry at a time; does nothing if there is no audio device.

    Everything plays on one reserved channel, and the narration is started by
    handle_event when the cry finishes rather than with pygame's Channel.queue:
    stopping a channel counts as finishing it, so a queued narration would
    start anyway and talk over the next entry's cry.
    """

    def __init__(
        self,
        paths: DataPaths,
        *,
        volume: float = 0.8,
        muted: bool = False,
        cry: bool = True,
        narration: bool = True,
    ) -> None:
        self._paths = paths
        self.volume = volume
        self.muted = muted
        self.cry = cry
        self.narration = narration
        self._channel: pygame.mixer.Channel | None = None
        self._next: pygame.mixer.Sound | None = None
        """The narration waiting for the cry to finish."""
        if not pygame.mixer.get_init():
            with suppress(pygame.error):  # no sound card or speaker: run silently
                pygame.mixer.init()
        if self.available:
            pygame.mixer.set_reserved(1)
            self._channel = pygame.mixer.Channel(0)
            self._channel.set_endevent(FINISHED)

    @property
    def available(self) -> bool:
        return pygame.mixer.get_init() is not None

    def play(self, mon: Pokemon) -> None:
        """Start the cry; its narration follows once the cry has finished."""
        if self.muted or self._channel is None:
            return
        sounds = [
            sound
            for enabled, path in ((self.cry, mon.cry_path), (self.narration, mon.narration_path))
            if enabled and (sound := self._load(path))
        ]
        self.stop()  # a new entry cuts off the previous one when browsing quickly
        if not sounds:
            return
        self._channel.play(sounds[0])
        self._next = sounds[1] if len(sounds) > 1 else None

    def handle_event(self, event: pygame.event.Event) -> None:
        """Start the waiting narration when the cry ends.

        Stopping the channel for a new entry also posts FINISHED; by then the
        new cry is playing, so the busy check stops the narration starting early.
        """
        if event.type != FINISHED or self._next is None or self._channel is None:
            return
        if not self._channel.get_busy():
            self._channel.play(self._next)
            self._next = None

    def _load(self, stored_path: str | None) -> pygame.mixer.Sound | None:
        if not stored_path:
            return None
        try:
            sound = pygame.mixer.Sound(self._paths.resolve(stored_path))
        except (FileNotFoundError, pygame.error):
            return None
        sound.set_volume(self.volume)
        return sound

    def stop(self) -> None:
        self._next = None  # first, so the FINISHED from stopping starts nothing
        if self._channel is not None:
            self._channel.stop()

    def apply(self, settings: Settings) -> None:
        """Follow the settings screen; turning sound off stops what is playing."""
        self.volume = settings.volume
        self.cry = settings.cry
        self.narration = settings.narration
        self.muted = not settings.sound
        if self.muted:
            self.stop()
