"""CLIP image and text encoders, run with ONNX Runtime (no PyTorch needed)."""

from pathlib import Path

import numpy as np
import onnxruntime as ort
import requests
from PIL import Image

MODELS_URL = "https://huggingface.co/Xenova/{model}/resolve/main/{file}"
DEFAULT_MODEL = "clip-vit-base-patch32"
"""Sized for the Pi Zero 2 W. clip-vit-base-patch16 is more accurate but several
times slower and too large for 512 MB unquantized."""
IMAGE_SIZE = 224
# CLIP's training normalisation.
MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
CONTEXT_LENGTH = 77


def ensure_model(model: str, models_dir: Path, *, files: tuple[str, ...]) -> Path:
    """Download any missing model files; returns the model's folder."""
    folder = models_dir / model
    folder.mkdir(parents=True, exist_ok=True)
    for name in files:
        dest = folder / name
        if dest.exists():
            continue
        remote = name if name == "tokenizer.json" else f"onnx/{name}"
        print(f"Downloading {model}/{name} ...")
        response = requests.get(MODELS_URL.format(model=model, file=remote), timeout=600)
        response.raise_for_status()
        dest.write_bytes(response.content)
    return folder


def _session(path: Path) -> ort.InferenceSession:
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _normalize(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.linalg.norm(vectors, axis=-1, keepdims=True)


def preprocess(image: Image.Image) -> np.ndarray:
    """Resize the short side to 224, centre-crop to a square, normalise: (3, 224, 224)."""
    image = image.convert("RGB")
    scale = IMAGE_SIZE / min(image.size)
    width, height = round(image.width * scale), round(image.height * scale)
    image = image.resize((width, height), Image.Resampling.BICUBIC)
    left, top = (width - IMAGE_SIZE) // 2, (height - IMAGE_SIZE) // 2
    image = image.crop((left, top, left + IMAGE_SIZE, top + IMAGE_SIZE))
    pixels = (np.asarray(image, dtype=np.float32) / 255 - MEAN) / STD
    return pixels.transpose(2, 0, 1)


class ImageEncoder:
    def __init__(self, model_dir: Path, *, quantized: bool = False) -> None:
        name = "vision_model_quantized.onnx" if quantized else "vision_model.onnx"
        self._session = _session(model_dir / name)

    def encode(self, images: list[Image.Image]) -> np.ndarray:
        """Unit-length vectors, one row per image."""
        batch = np.stack([preprocess(image) for image in images])
        (embeds,) = self._session.run(["image_embeds"], {"pixel_values": batch})
        return _normalize(embeds)


class TextEncoder:
    """Only needed on the PC, to build the per-Pokémon vectors."""

    def __init__(self, model_dir: Path) -> None:
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(CONTEXT_LENGTH)
        self._tokenizer.enable_padding(length=CONTEXT_LENGTH)
        self._session = _session(model_dir / "text_model.onnx")

    def encode(self, texts: list[str]) -> np.ndarray:
        ids = np.array([e.ids for e in self._tokenizer.encode_batch(texts)], dtype=np.int64)
        (embeds,) = self._session.run(["text_embeds"], {"input_ids": ids})
        return _normalize(embeds)
