"""The main loop: buttons in, screen and sound out.

The screen only redraws after a button press, and the loop naps between
checks, which keeps the Pico's power draw low on battery.
"""

import time

from dex import hardware, state
from dex.audio import EntryAudio
from dex.index import Dex
from dex.records import Records
from dex.screens import UI, Fonts
from dex.settings import Settings
from dex.timing import Repeater, ScreenSleep

DATA = hardware.SD_MOUNT + "/pokedex"
SETTINGS_FILE = hardware.SD_MOUNT + "/settings.json"
NAP = 0.01
"""Seconds between checks for button presses and the end of the cry."""
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
    st = state.PokedexState(dex, records.entry, Settings.load(SETTINGS_FILE))
    audio = EntryAudio(hardware.audio_out(), records)
    audio.apply(st.settings)
    keys = hardware.buttons()
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
                backlight.set(True)  # the press that wakes the screen does nothing else
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
            display.refresh()
        elif sleep.due(st.settings.sleep_minutes, now):
            sleep.asleep = True
            audio.stop()
            backlight.set(False)


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
    if state.audio_due(before, st) or st.replay:
        st.replay = False
        audio.play(st.selected_id)
    elif st.view != state.DETAIL and before[0] == state.DETAIL:
        audio.stop()  # leaving the entry ends its narration
    ui.show(st)
