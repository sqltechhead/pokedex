"""The main loop: buttons in, screen and sound out.

The screen only redraws after a button press, and the loop naps between
checks, which keeps the Pico's power draw low on battery.
"""

import time

from dex import hardware, state
from dex.audio import EntryAudio
from dex.browse import Browse
from dex.index import Dex
from dex.records import Records
from dex.screens import UI, Fonts
from dex.settings import Settings
from dex.timing import Repeater, ScreenSleep

DATA = hardware.SD_MOUNT + "/pokedex"
SETTINGS_FILE = hardware.SD_MOUNT + "/settings.json"
NAP = 0.01
"""Seconds between checks for button presses and the end of the cry."""
SPLASH_SECONDS = (1.5, 3.0)
"""The start-up screen stays at least this long, and at most this long while the
jingle (about 1.3 s) plays."""
BATTERY_EVERY = 30000
"""Milliseconds between battery readings."""


def now_ms():
    return time.monotonic_ns() // 1000000


def run():
    display = hardware.display()
    backlight = hardware.Backlight(display)
    ui = UI(display, Fonts(), None)
    try:
        hardware.mount_sd()
        dex = Dex.load(DATA + "/index.tsv")
    except OSError:
        ui.message("NO SD CARD", "Put in the Pokedex SD card, then press RESET.")
        display.refresh()
        while True:
            time.sleep(1)

    records = Records(DATA)
    ui = UI(display, Fonts(DATA + "/fonts"), records)
    settings = Settings.load(SETTINGS_FILE)
    st = state.PokedexState(dex, records.entry, settings, browse=Browse(DATA + "/cat", dex))
    backlight.set(True, st.settings.backlight)
    audio = EntryAudio(hardware.audio_out(), records)
    audio.apply(st.settings)
    keys = hardware.buttons()
    start_up(ui, display, audio, keys)
    sleep = ScreenSleep(now_ms())
    repeater = Repeater()
    meter = hardware.Battery()
    next_reading = 0
    ui.show(st)
    display.refresh()

    while True:
        time.sleep(NAP)
        audio.poll()
        now = now_ms()
        actions = []
        event = keys.events.get()
        while event:
            action = hardware.BUTTON_ACTIONS[event.key_number]
            if event.released:
                repeater.release(action)
            elif sleep.note_input(now):
                # The press that wakes the screen does nothing else.
                backlight.set(True, st.settings.backlight)
            else:
                repeater.press(action, now, state.DPAD)
                actions.append(action)
            event = keys.events.get()
        held = repeater.due(now)
        if held is not None:
            actions.append(held)

        if now >= next_reading:
            next_reading = now + BATTERY_EVERY
            ui.battery.show(meter.volts())
            if not sleep.asleep and not actions:
                display.refresh()

        if actions:
            sleep.last_input = now
            handle(actions, st, ui, audio)
            backlight.set(True, st.settings.backlight)
            display.refresh()
        elif sleep.due(st.settings.sleep_minutes, now):
            sleep.asleep = True
            audio.stop()
            backlight.set(False)


def start_up(ui, display, audio, keys):
    """The splash screen while the jingle plays; any button skips it."""
    ui.splash()
    display.refresh()
    audio.play_paths([DATA + "/sfx/startup.wav"])
    shortest, longest = SPLASH_SECONDS
    start = time.monotonic()
    while True:
        audio.poll()
        elapsed = time.monotonic() - start
        if keys.events.get() or elapsed > longest or (elapsed > shortest and not audio.busy):
            break
        time.sleep(NAP)
    audio.stop()
    keys.events.clear()


def handle(actions, st, ui, audio):
    """Apply the presses, then save settings, play or stop audio and redraw."""
    before = (st.view, st.selected_id)
    settings_before = st.settings
    for action in actions:
        st.handle(action)

    if st.settings != settings_before:
        audio.apply(st.settings)
        saved = st.settings.save(SETTINGS_FILE)
        ui.notice = "" if saved else "Couldn't save settings: is the SD card locked?"
    if st.quiz_sound:
        target = st.dex.ids[st.quiz.target]
        sfx = DATA + "/sfx/" + st.quiz_sound + ".wav"
        audio.play_paths([sfx, ui.records.existing("cry", target, "wav")])
        st.quiz_sound = None
    elif state.audio_due(before, st) or st.replay:
        st.replay = False
        audio.play(st.selected_id)
    elif st.view != before[0] and before[0] in (state.DETAIL, state.QUIZ):
        audio.stop()  # leaving the entry or quiz ends its sound
    ui.show(st)
