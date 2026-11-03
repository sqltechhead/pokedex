"""Stand-in for a module blinka-displayio-pygamedisplay 4.1.0 imports but doesn't ship.

The simulator reads buttons itself (see pokedex_sim.KeyboardButtons), so the
display only needs this import to succeed.
"""


class PyGameKeys:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("use pokedex_sim.KeyboardButtons instead")
