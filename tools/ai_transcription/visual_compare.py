"""Semantic comparison used by the image-to-DB visual round-trip gate."""

from __future__ import annotations

from fractions import Fraction


def semantic_maps(payload: dict) -> tuple[
    dict[int, dict[Fraction, tuple[int, ...]]],
    dict[int, dict[tuple[Fraction, str, str, int], int]],
]:
    events: dict[int, dict[Fraction, tuple[int, ...]]] = {}
    rests: dict[int, dict[tuple[Fraction, str, str, int], int]] = {}
    for measure in payload["measures"]:
        number = int(measure["number"])
        event_map: dict[Fraction, tuple[int, ...]] = {}
        for event in measure.get("events", []):
            onset = Fraction(str(event["time"]))
            event_map[onset] = tuple(
                sorted(int(pitch) for pitch in event["pitches"])
            )
        events[number] = event_map
        rest_map: dict[tuple[Fraction, str, str, int], int] = {}
        for rest in measure.get("rests", []):
            key = (
                Fraction(str(rest["time"])),
                str(rest.get("voice", "up")),
                str(rest.get("duration", "quarter")),
                int(rest.get("dots", 0)),
            )
            rest_map[key] = rest_map.get(key, 0) + 1
        rests[number] = rest_map
    return events, rests


def compare_semantic_payloads(expected: dict, actual: dict) -> list[str]:
    expected_events, expected_rests = semantic_maps(expected)
    actual_events, actual_rests = semantic_maps(actual)
    errors = []
    if len(expected["measures"]) != len(actual["measures"]):
        errors.append(
            f"measure count: expected {len(expected['measures'])}, "
            f"got {len(actual['measures'])}"
        )
    for expected_measure, actual_measure in zip(
        expected["measures"],
        actual["measures"],
    ):
        number = int(expected_measure["number"])
        if int(expected_measure["length"]) != int(actual_measure["length"]):
            errors.append(
                f"measure {number}: meter {expected_measure['length']}/4 -> "
                f"{actual_measure['length']}/4"
            )
        expected_event_map = expected_events[number]
        actual_event_map = actual_events.get(number, {})
        if expected_event_map != actual_event_map:
            errors.append(
                f"measure {number}: note difference "
                f"missing={sorted(set(expected_event_map.items()) - set(actual_event_map.items()))[:4]} "
                f"extra={sorted(set(actual_event_map.items()) - set(expected_event_map.items()))[:4]}"
            )
        expected_rest_map = expected_rests[number]
        actual_rest_map = actual_rests.get(number, {})
        if expected_rest_map != actual_rest_map:
            errors.append(
                f"measure {number}: rest difference "
                f"missing={sorted(set(expected_rest_map.items()) - set(actual_rest_map.items()))[:4]} "
                f"extra={sorted(set(actual_rest_map.items()) - set(expected_rest_map.items()))[:4]}"
            )
    return errors
