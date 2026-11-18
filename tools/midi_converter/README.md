# MIDI Converter for DB Score

`midi-converter` converts audio-to-MIDI drum performances into deterministic,
notation-friendly Standard MIDI Files for DB Score.

The first implementation targets YuE2 exports:

- reads General MIDI percussion from MIDI channel 10;
- uses note-on events as percussion attacks and ignores synthetic note lengths;
- preserves velocity and every distinct pitch/attack;
- removes only exact duplicate note-on events at the same tick and pitch;
- automatically chooses a straight or triplet grid;
- separates nearby hits of the same drum instead of silently merging them;
- emits tempo, time signature, and a drum-only MIDI track;
- verifies the written file by parsing it again before reporting success.

## Build

```sh
cmake -S tools/midi_converter -B build-midi-converter
cmake --build build-midi-converter
```

## Inspect

```sh
midi-converter inspect --input "drums.mid"
```

## Normalize

```sh
midi-converter normalize \
  --input "drums.mid" \
  --output "drums-standard.mid" \
  --report "drums-standard.json" \
  --grid auto \
  --bpm auto
```

Supported grid values are `auto`, `8`, `8t`, `16`, `16t`, `32`, and `32t`.
The `t` variants are triplets.

`--bpm auto` estimates the pulse from recurring kick and snare intervals. This
fixes files whose MIDI tempo metadata says 120 BPM even though the transcribed
drum performance has a different underlying pulse. Use `--bpm source` to keep
the MIDI tempo or pass a numeric BPM to override it.

## Regression tests

```sh
ctest --test-dir build-midi-converter --output-on-failure
```

## End-to-end DB Score test

```sh
python3 tools/midi_converter/tests/verify_dbscore.py \
  --converter build-midi-converter/midi-converter \
  --dbscore "/Applications/DB score制谱大师.app/Contents/MacOS/dbscore" \
  --input "drums.mid" \
  --bpm auto
```

For a directory containing multiple test files:

```sh
python3 tools/midi_converter/tests/run_batch.py \
  --converter build-midi-converter/midi-converter \
  --dbscore "/Applications/DB score制谱大师.app/Contents/MacOS/dbscore" \
  --input-dir test-midis \
  --output-dir test-results \
  --bpm auto
```
