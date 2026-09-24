"""sound.seed: the catalogue measure (duration, bpm, key, energy; decision 7.2) and the
seed-time sweep check (7.3). The measurements are numpy over samples ffmpeg decoded, so
the pure functions are tested on numpy-synthesised signals with known content, and the
two commands on a temporary catalogue built with ffmpeg (12.1: nothing committed)."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from shortsmith import sound
from shortsmith.fixture import make_wav
from shortsmith.sound import seed
from tests.conftest import Sounds

SR = seed.MEASURE_RATE
NOTE_MIDI = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7,
             "G#": 8, "Ab": 8, "A": 9, "Bb": 10, "B": 11}  # fmt: skip


def _hz(note: str) -> float:
    """'A3' -> 220.0: scientific pitch, A4 = 440 Hz."""
    name, octave = note[:-1], int(note[-1])
    midi = 12 * (octave + 1) + NOTE_MIDI[name]
    return 440.0 * 2 ** ((midi - 69) / 12)


def _chords(chords: list[tuple[str, ...]], *, each_s: float = 1.0) -> np.ndarray:
    """Each chord's notes as equal sines for `each_s`, one after another."""
    t = np.arange(round(each_s * SR)) / SR
    parts = [sum(np.sin(2 * np.pi * _hz(n) * t) for n in chord) / len(chord) for chord in chords]
    return 0.5 * np.concatenate(parts)


# The exact note content of each key's signal: i-iv-V-i in the minor keys (the raised
# leading tone in V), I-IV-V-I in the major ones. A minor and C major are relatives
# (the same seven notes); D major and D minor are a non-relative pair on the same tonic.
A_MINOR = [("A3", "C4", "E4"), ("D4", "F4", "A4"), ("E3", "G#3", "B3"), ("A3", "C4", "E4")]
C_MAJOR = [("C4", "E4", "G4"), ("F3", "A3", "C4"), ("G3", "B3", "D4"), ("C4", "E4", "G4")]
D_MAJOR = [("D4", "F#4", "A4"), ("G3", "B3", "D4"), ("A3", "C#4", "E4"), ("D4", "F#4", "A4")]
D_MINOR = [("D4", "F4", "A4"), ("G3", "Bb3", "D4"), ("A3", "C#4", "E4"), ("D4", "F4", "A4")]


def _top_notes(chroma: np.ndarray, n: int = 3) -> set[str]:
    return {seed.PITCH_CLASSES[i] for i in np.argsort(chroma)[-n:]}


# --- key ---------------------------------------------------------------------------------


def test_a_minor_is_am_and_its_chroma_is_the_tonic_triad() -> None:
    chroma = seed.chroma(_chords(A_MINOR), SR)
    assert _top_notes(chroma) == {"A", "C", "E"}
    assert seed.key_name(chroma) == "Am"


def test_c_major_is_c_and_its_chroma_is_the_tonic_triad() -> None:
    chroma = seed.chroma(_chords(C_MAJOR), SR)
    assert _top_notes(chroma) == {"C", "E", "G"}
    assert seed.key_name(chroma) == "C"


@pytest.mark.parametrize(("chords", "key"), [(D_MAJOR, "D"), (D_MINOR, "Dm")])
def test_a_non_relative_pair_is_told_apart(chords: list[tuple[str, ...]], key: str) -> None:
    assert seed.key_name(seed.chroma(_chords(chords), SR)) == key


def test_silence_has_no_key() -> None:
    assert seed.key_name(seed.chroma(np.zeros(SR), SR)) is None


# --- tempo -------------------------------------------------------------------------------


def _clicks(bpm: float, *, seconds: float = 20.0) -> np.ndarray:
    """A 1 kHz blip on every beat, 30 ms long."""
    x = np.zeros(round(seconds * SR))
    blip = np.sin(2 * np.pi * 1000 * np.arange(round(0.03 * SR)) / SR) * 0.5
    for start in np.arange(0.0, seconds - 0.05, 60.0 / bpm):
        i = round(start * SR)
        x[i : i + blip.size] += blip
    return x


@pytest.mark.parametrize("bpm", [100, 128])
def test_the_tempo_of_a_click_track(bpm: int) -> None:
    measured = seed.tempo_bpm(_clicks(bpm), SR)
    assert measured is not None and abs(measured - bpm) <= 1, measured


def test_a_steady_tone_has_no_tempo() -> None:
    t = np.arange(5 * SR) / SR
    assert seed.tempo_bpm(0.3 * np.sin(2 * np.pi * 220 * t), SR) is None


# --- energy ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("per_s", "energy"),
    [(0.0, 1), (0.49, 1), (0.5, 2), (1.49, 2), (1.5, 3), (3.0, 4), (4.99, 4), (5.0, 5)],
)
def test_energy_buckets_the_onset_rate(per_s: float, energy: int) -> None:
    assert seed.energy_level(per_s) == energy


def test_dense_onsets_measure_more_energy_than_sparse() -> None:
    # 45 BPM over 20 s is 15 onsets, 0.75 a second; 360 BPM is 6 a second
    assert seed.onset_rate(_clicks(45), SR) == pytest.approx(0.75)
    sparse = seed.energy_level(seed.onset_rate(_clicks(45), SR))
    dense = seed.energy_level(seed.onset_rate(_clicks(360), SR))
    assert (sparse, dense) == (2, 5)


# --- the commands on a catalogue ---------------------------------------------------------

HEADER = "# the operator's header comment, kept by measure\n\n"
C_MAJOR_PULSE = (  # C major at 120 BPM: a triad struck every half second
    "0.25*(sin(2*PI*261.63*t)+sin(2*PI*329.63*t)+sin(2*PI*392*t))*exp(-8*mod(t,0.5))"
)


def _catalogue(root: Path, sfx: Path) -> Path:
    """An operator-shaped catalogue: ids, files, sources and tags only - every measured
    field is left for `measure` to fill."""
    files = root / "files"
    files.mkdir(parents=True)
    make_wav(files / "bed.wav", expr=C_MAJOR_PULSE, duration_s=12.0)
    shutil.copy(sfx, files / "hit.wav")
    entries = [
        {"id": "bed_c", "kind": "bed", "file": "files/bed.wav", "source": "synthetic",
         "source_url": "https://example.test/bed", "licence": "CC0-1.0",
         "tags": {"theme": ["tech"], "mood": ["bright"], "intent": []}},
        {"id": "sfx_hit", "kind": "sfx", "file": "files/hit.wav", "source": "synthetic",
         "source_url": "https://example.test/hit", "licence": "CC0-1.0",
         "tags": {"theme": [], "mood": [], "intent": ["drum"]}},
    ]  # fmt: skip
    path = root / "catalog.yaml"
    path.write_text(HEADER + yaml.safe_dump({"entries": entries}, sort_keys=False), "utf-8")
    return path


def test_measure_fills_every_measured_field(tmp_path: Path, sounds: Sounds) -> None:
    path = _catalogue(tmp_path, sounds("clicks"))
    assert seed.main(["measure", "--catalogue", str(path)]) == 0
    text = path.read_text(encoding="utf-8")
    assert text.startswith(HEADER), "the header comment survives"
    library = sound.load_catalogue(path)
    bed = library.entry("bed_c")
    hit = library.entry("sfx_hit")
    assert bed is not None and hit is not None
    assert bed.duration_s == pytest.approx(12.0, abs=0.01)
    assert bed.bpm is not None and abs(bed.bpm - 120) <= 1
    assert bed.key == "C"
    assert 1 <= bed.energy <= 5
    assert hit.duration_s == pytest.approx(2.0, abs=0.01)
    assert (hit.bpm, hit.key) == (None, None), "an SFX has no tempo or key"
    assert hit.tags.intent == ["drum"] and bed.tags.theme == ["tech"]


def test_measure_names_a_missing_file_and_writes_nothing(
    tmp_path: Path, sounds: Sounds, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _catalogue(tmp_path, sounds("clicks"))
    (tmp_path / "files" / "hit.wav").unlink()
    before = path.read_text(encoding="utf-8")
    assert seed.main(["measure", "--catalogue", str(path)]) == 1
    assert "sfx_hit" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == before


def test_measure_leaves_an_empty_catalogue_untouched(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text(HEADER + "entries: []\n", encoding="utf-8")
    assert seed.main(["measure", "--catalogue", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == HEADER + "entries: []\n"


def test_check_passes_clean_sfx(
    library: sound.Library, capsys: pytest.CaptureFixture[str]
) -> None:
    catalogue = library.root / "catalog.yaml"
    assert seed.main(["check", "--catalogue", str(catalogue)]) == 0
    assert f"{len(library.sfx())} sfx files clean" in capsys.readouterr().out


def test_check_fails_naming_the_file_and_the_rule(
    tmp_path: Path, sounds: Sounds, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _catalogue(tmp_path, sounds("noise_500ms"))
    seed.main(["measure", "--catalogue", str(path)])
    capsys.readouterr()
    assert seed.main(["check", "--catalogue", str(path)]) == 1
    err = capsys.readouterr().err
    assert "sfx_hit" in err and "files/hit.wav" in err and "R1" in err
