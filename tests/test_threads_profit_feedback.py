from app.social.threads.profit_feedback import _score


def test_profitable_content_beats_loss_making_content():
    profitable, _ = _score({
        "clicks": 500,
        "orders": 20,
        "profit": 143000,
        "revenue": 598000,
        "confidence": 0.86,
        "returns": 1,
    })
    loss, _ = _score({
        "clicks": 2000,
        "orders": 20,
        "profit": -30000,
        "revenue": 598000,
        "confidence": 0.90,
        "returns": 4,
    })
    assert profitable > loss
    assert profitable >= 70
    assert loss <= 35


def test_small_sample_is_shrunk_toward_neutral():
    score, breakdown = _score({
        "clicks": 3,
        "orders": 1,
        "profit": 50000,
        "revenue": 60000,
        "confidence": 0.95,
        "returns": 0,
    })
    assert 45 <= score <= 65
    assert breakdown["sample_maturity"] < 20


def test_return_rate_reduces_score():
    clean, _ = _score({"clicks": 200, "orders": 10, "profit": 100000, "revenue": 300000, "confidence": 0.8, "returns": 0})
    returned, _ = _score({"clicks": 200, "orders": 10, "profit": 100000, "revenue": 300000, "confidence": 0.8, "returns": 4})
    assert clean > returned
