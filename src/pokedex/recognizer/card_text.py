"""Reading the Pokémon's name off a trading card.

Uses PaddleOCR's small English models (via RapidOCR's ONNX exports): one
finds text regions, the other reads each region. Pre- and post-processing
are done with numpy and scipy so neither OpenCV nor PaddlePaddle is needed,
which keeps the Pi Zero install small.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import onnxruntime as ort
import requests
from PIL import Image
from scipy import ndimage

MODELS_URL = "https://huggingface.co/SWHL/RapidOCR/resolve/main/{folder}/{file}"
MODEL_FILES = {
    "en_PP-OCRv3_det_infer.onnx": "PP-OCRv4",  # RapidOCR files the v3 English detector here
    "en_PP-OCRv3_rec_infer.onnx": "PP-OCRv3",
}
MODEL_DIR = "ppocr-v3-en"

DETECT_SIDE = 480
"""Longest side the detector sees. Card names are large, so small is enough (and fast)."""
MAX_REGIONS = 8
"""Only the tallest text regions are read: the name is one of the biggest on a card."""
MIN_NAME_SIMILARITY = 0.8
# PaddleOCR's normalisation, applied to BGR channel order like its OpenCV pipeline.
DET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
REC_HEIGHT = 48


@dataclass(frozen=True)
class TextRegion:
    text: str
    box: tuple[int, int, int, int]
    """left, top, right, bottom in image pixels."""

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


@dataclass(frozen=True)
class CardName:
    pokemon_id: int
    similarity: float
    text: str


def ensure_models(models_dir: Path) -> Path:
    folder = models_dir / MODEL_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name, remote_folder in MODEL_FILES.items():
        if not (folder / name).exists():
            print(f"Downloading {name} ...")
            response = requests.get(MODELS_URL.format(folder=remote_folder, file=name), timeout=300)
            response.raise_for_status()
            (folder / name).write_bytes(response.content)
    return folder


def normalize_name(text: str) -> str:
    """Letters and digits only, lower case: "Farfetch’d" -> "farfetchd"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if c.isascii() and c.isalnum()).lower()


class CardReader:
    def __init__(self, model_dir: Path, names: Iterable[tuple[int, str]]) -> None:
        options = ort.SessionOptions()
        options.log_severity_level = 3
        self._detector = ort.InferenceSession(
            str(model_dir / "en_PP-OCRv3_det_infer.onnx"), options, ["CPUExecutionProvider"]
        )
        self._reader = ort.InferenceSession(
            str(model_dir / "en_PP-OCRv3_rec_infer.onnx"), options, ["CPUExecutionProvider"]
        )
        characters = self._reader.get_modelmeta().custom_metadata_map["character"].splitlines()
        self._alphabet = ["", *characters, " "]  # CTC blank first, space last
        self._names = [(pid, normalize_name(name)) for pid, name in names]

    def read(self, image: Image.Image) -> list[TextRegion]:
        """Text regions, tallest first (at most MAX_REGIONS); useful for debugging."""
        regions = [
            TextRegion(self._recognise(image.crop(b)), b) for b in self._tallest_boxes(image)
        ]
        return [r for r in regions if r.text.strip()]

    def _tallest_boxes(self, image: Image.Image) -> list[tuple[int, int, int, int]]:
        boxes = sorted(self._detect(image), key=lambda b: b[3] - b[1], reverse=True)
        return boxes[:MAX_REGIONS]

    def find_name(self, image: Image.Image) -> CardName | None:
        """The Pokémon whose name is printed on the card, if one can be read.

        Reads regions tallest first and stops at the first name, so "Evolves
        from Ivysaur" in small print does not beat a card's big "Venusaur"
        title, and the slow reading step runs as few times as possible.
        """
        for box in self._tallest_boxes(image):
            match = self.match_name(self._recognise(image.crop(box)))
            if match is not None:
                return match
        return None

    def match_name(self, text: str) -> CardName | None:
        best: CardName | None = None
        for word in _candidates(text):
            if len(word) < 3:
                continue
            for pid, name in self._names:
                similarity = SequenceMatcher(None, word, name).ratio()
                if similarity >= MIN_NAME_SIMILARITY and (
                    best is None or similarity > best.similarity
                ):
                    best = CardName(pid, similarity, text)
        return best

    def _detect(self, image: Image.Image) -> list[tuple[int, int, int, int]]:
        rgb = image.convert("RGB")
        scale = min(1.0, DETECT_SIDE / max(rgb.size))
        width = max(32, round(rgb.width * scale / 32) * 32)
        height = max(32, round(rgb.height * scale / 32) * 32)
        pixels = np.asarray(rgb.resize((width, height), Image.Resampling.BILINEAR), np.float32)
        pixels = (pixels[:, :, ::-1] / 255 - DET_MEAN) / DET_STD  # RGB -> BGR, normalise
        (probability,) = self._detector.run(None, {"x": pixels.transpose(2, 0, 1)[None]})
        probability = probability[0, 0]

        labels, _ = ndimage.label(probability > 0.3)
        boxes = []
        sx, sy = rgb.width / width, rgb.height / height
        for index, found in enumerate(ndimage.find_objects(labels), 1):
            rows, cols = found
            h, w = rows.stop - rows.start, cols.stop - cols.start
            if h < 3 or w < 3 or probability[found][labels[found] == index].mean() < 0.6:
                continue
            # DBNet predicts shrunk text cores; grow them back out (its "unclip" step).
            grow = 1.5 * w * h / (2 * (w + h))
            left, top = (cols.start - grow) * sx, (rows.start - grow) * sy
            right, bottom = (cols.stop + grow) * sx, (rows.stop + grow) * sy
            boxes.append((
                max(0, round(left)), max(0, round(top)),
                min(rgb.width, round(right)), min(rgb.height, round(bottom)),
            ))  # fmt: skip
        return boxes

    def _recognise(self, crop: Image.Image) -> str:
        crop = crop.convert("RGB")
        width = max(REC_HEIGHT, min(1280, round(crop.width * REC_HEIGHT / max(1, crop.height))))
        pixels = np.asarray(crop.resize((width, REC_HEIGHT), Image.Resampling.BILINEAR), np.float32)
        pixels = (pixels[:, :, ::-1] / 255 - 0.5) / 0.5
        (probabilities,) = self._reader.run(None, {"x": pixels.transpose(2, 0, 1)[None]})
        best = probabilities[0].argmax(axis=1)
        # CTC: collapse repeats, then drop blanks.
        kept = [i for n, i in enumerate(best) if i != 0 and (n == 0 or i != best[n - 1])]
        return "".join(self._alphabet[i] for i in kept if i < len(self._alphabet))


def _candidates(text: str) -> list[str]:
    """The whole line and each word, normalised: "Bulbasaur HP80" -> bulbasaurhp80, bulbasaur..."""
    words = [normalize_name(w) for w in re.split(r"\s+", text)]
    return [normalize_name(text), *words]
