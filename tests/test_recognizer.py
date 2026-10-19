import time

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("onnxruntime")
from PIL import Image  # noqa: E402

from pokedex.camera import square_crop  # noqa: E402
from pokedex.models import BaseStats, Pokemon  # noqa: E402
from pokedex.recognizer.clip import IMAGE_SIZE, preprocess  # noqa: E402
from pokedex.recognizer.matcher import rank  # noqa: E402
from pokedex.recognizer.references import References, prompts_for  # noqa: E402


def unit(*values: float) -> np.ndarray:
    vector = np.array(values, dtype=np.float32)
    return vector / np.linalg.norm(vector)


@pytest.fixture
def references() -> References:
    # Three Pokémon in a toy 3-D space: text and artwork vectors per row.
    return References(
        ids=np.array([1, 4, 7]),
        text=np.stack([unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1)]),
        image=np.stack([unit(1, 0.1, 0), unit(0, 1, 0.1), unit(0.1, 0, 1)]),
        model="toy",
    )


def test_rank_orders_by_blended_similarity(references: References):
    matches = rank(references, unit(0.2, 1, 0), text_weight=0.5, top=3)
    assert [m.pokemon_id for m in matches] == [4, 1, 7]
    assert matches[0].confidence > 0.9
    assert sum(m.confidence for m in matches) == pytest.approx(1, abs=1e-6)


def test_text_weight_changes_which_source_counts(references: References):
    query = unit(1, 0, 1)  # equally like #1's text and #7's text
    by_artwork = rank(references, query, text_weight=0.0, top=1)[0].pokemon_id
    assert by_artwork in (1, 7)


def test_references_round_trip(tmp_path, references: References):
    path = tmp_path / "refs.npz"
    references.save(path)
    loaded = References.load(path)
    assert loaded.model == "toy"
    np.testing.assert_array_equal(loaded.ids, references.ids)
    np.testing.assert_allclose(loaded.image, references.image)


def test_preprocess_shape_and_crop():
    pixels = preprocess(Image.new("RGB", (640, 360), (255, 0, 0)))
    assert pixels.shape == (3, IMAGE_SIZE, IMAGE_SIZE)
    assert pixels[0].mean() > 1.5  # red channel well above CLIP's mean
    assert pixels[1].mean() < -1.5


def test_square_crop_takes_the_centre():
    frame = Image.new("RGB", (640, 360))
    frame.paste((255, 255, 255), (140, 0, 500, 360))  # the centre 360 square is white
    crop = square_crop(frame)
    assert crop.size == (360, 360)
    assert crop.getpixel((0, 0)) == (255, 255, 255)


def test_prompts_include_name_and_genus():
    mon = Pokemon(
        id=25,
        name="Pikachu",
        genus="Mouse Pokémon",
        type1="electric",
        height_dm=4,
        weight_hg=60,
        stats=BaseStats(hp=1, attack=1, defense=1, sp_attack=1, sp_defense=1, speed=1),
    )
    prompts = prompts_for(mon)
    assert "a photo of a Pikachu plush toy" in prompts
    assert "Pikachu, the Mouse Pokémon" in prompts


def test_ffmpeg_camera_reads_frames():
    pytest.importorskip("imageio_ffmpeg")
    from pokedex.camera import FFmpegCamera

    camera = FFmpegCamera(input_args=["-re", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30"])
    try:
        for _ in range(50):
            if camera.latest() is not None:
                break
            time.sleep(0.1)
        frame = camera.latest()
        assert frame is not None
        assert frame.size == (640, 360)
        assert camera.error() is None
    finally:
        camera.close()
