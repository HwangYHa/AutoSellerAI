from app.social.threads.marketing_playbook import score_threads_playbook


def test_playbook_rewards_hook_readability_and_engagement():
    product = {"name": "휴대용 미니 선풍기", "brand": "Breeze", "material": "ABS"}
    body = (
        "여름에 선풍기 하나만 잘 골라도 체감이 꽤 달라지지 않아?\n\n"
        "ABS 소재에 휴대용 디자인이라 가방에 넣고 다니기 좋게 보이더라.\n\n"
        "너는 이런 거 살 때 무게부터 봐, 디자인부터 봐? 댓글로 알려줘."
    )

    score, checks = score_threads_playbook(body, product, "https://cdn.example.com/fan.png")

    assert score >= 80
    assert checks["strong_hook"] is True
    assert checks["short_readable"] is True
    assert checks["value_proof"] is True
    assert checks["visual_ready"] is True
    assert checks["engagement"] is True


def test_playbook_penalizes_product_first_ad_copy():
    product = {"name": "휴대용 미니 선풍기"}
    body = "휴대용 미니 선풍기 추천합니다. 지금 구매하세요."

    score, checks = score_threads_playbook(body, product, "")

    assert score < 60
    assert checks["broad_topic"] is False
    assert checks["strong_hook"] is False
    assert checks["short_readable"] is False
    assert checks["visual_ready"] is False
