"""Recognising Pokémon plushies, figures and cards from a camera photo.

CLIP turns images and text into vectors that sit close together when they
show the same thing. ``pokedex-embed`` precomputes a vector per Pokémon on a
PC; the device only encodes the camera frame and finds the nearest one.

Needs the optional extra: ``uv sync --extra recognize``.
"""
