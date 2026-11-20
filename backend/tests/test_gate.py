"""@spec: 002-anonymization-reid-gate"""

from financequest.engine.gate import StoryClock, gate_beats, gate_chart


def test_gate_drops_after_today():
    pts = [(0, 1), (10, 2), (11, 3), (30, 4)]
    assert gate_chart(pts, StoryClock(10), lambda p: p[0]) == [(0, 1), (10, 2)]
    assert gate_beats(pts, StoryClock(-1), lambda p: p[0]) == []
