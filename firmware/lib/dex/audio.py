"""Playing an entry's audio: the Pokémon's cry, then the Pokédex reading the entry.

Files on the SD card are mono 16-bit WAV at SAMPLE_RATE (``pokedex-sdcard``
converts them), streamed from the card through one mixer voice, so volume
can change without re-encoding anything.
"""

import audiocore
import audiomixer
import pins

SAMPLE_RATE = pins.AUDIO_RATE


class EntryAudio:
    """Plays one entry at a time. The narration starts from poll() once the cry ends."""

    def __init__(self, output, records):
        self._records = records
        self._mixer = audiomixer.Mixer(
            voice_count=1,
            sample_rate=SAMPLE_RATE,
            channels=1,
            bits_per_sample=16,
            samples_signed=True,
            buffer_size=4096,  # a larger buffer rides out slow SD card reads
        )
        output.play(self._mixer)
        self._buffer = bytearray(2048)
        self._file = None
        self._next = []
        """What plays after the current sound, e.g. the narration after the cry."""
        self.enabled = True
        self.cry = True
        self.narration = True

    def play(self, pokemon_id):
        """Start the cry; its narration follows once the cry has finished."""
        paths = []
        if self.cry:
            paths.append(self._records.existing("cry", pokemon_id, "wav"))
        if self.narration:
            paths.append(self._records.existing("say", pokemon_id, "wav"))
        self.play_paths(paths)

    def play_paths(self, paths):
        """Play these files one after another (missing ones, given as None, are skipped)."""
        self.stop()  # a new sound cuts off the last one when browsing quickly
        paths = [path for path in paths if path]
        if self.enabled and paths:
            self._start(paths[0])
            self._next = paths[1:]

    @property
    def busy(self):
        return self._mixer.voice[0].playing or bool(self._next)

    def poll(self):
        """Call often from the main loop: starts the narration when the cry ends."""
        if self._mixer.voice[0].playing:
            return
        self._close()
        if self._next:
            path, self._next = self._next[0], self._next[1:]
            self._start(path)

    def stop(self):
        self._next = []
        self._mixer.voice[0].stop()
        self._close()

    def apply(self, settings):
        """Follow the settings screen; turning sound off stops what is playing."""
        self._mixer.voice[0].level = settings.level
        self.enabled = settings.sound
        self.cry = settings.cry
        self.narration = settings.narration
        if not self.enabled:
            self.stop()

    def _start(self, path):
        try:
            self._file = open(path, "rb")  # noqa: SIM115 - stays open while it streams
            self._mixer.voice[0].play(audiocore.WaveFile(self._file, self._buffer))
        except (OSError, ValueError):  # missing or not a WAV file this mixer can play
            self._close()

    def _close(self):
        if self._file is not None:
            self._file.close()
            self._file = None
