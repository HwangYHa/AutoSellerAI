from app.os.bulk_market_tools import _extract_remote_product


def test_coupang_category_id_is_not_forwarded_to_naver_and_options_are_preserved():
    raw = {
        "sellerProductName": "테스트 상품",
        "displayCategoryCode": 56101,
        "items": [
            {
                "salePrice": 12000,
                "itemName": "테스트 상품 빨강 S",
                "attributes": [
                    {"attributeTypeName": "색상", "attributeValueName": "빨강"},
                    {"attributeTypeName": "사이즈", "attributeValueName": "S"},
                ],
                "images": [],
                "contents": [],
            },
            {
                "salePrice": 12000,
                "itemName": "테스트 상품 파랑 M",
                "attributes": [
                    {"attributeTypeName": "색상", "attributeValueName": "파랑"},
                    {"attributeTypeName": "사이즈", "attributeValueName": "M"},
                ],
                "images": [],
                "contents": [],
            },
        ],
    }
    product = _extract_remote_product("coupang", "123", raw)
    assert product["category"] == ""
    assert product["source_category_id"] == "56101"
    assert product["options"] == [
        {"name": "색상", "values": ["빨강", "파랑"]},
        {"name": "사이즈", "values": ["S", "M"]},
    ]


def test_naver_category_id_is_not_forwarded_to_coupang_and_options_are_preserved():
    raw = {
        "originProduct": {
            "name": "네이버 테스트 상품",
            "salePrice": 15000,
            "leafCategoryId": "50000641",
            "images": {"representativeImage": {"url": "https://example.com/a.jpg"}},
            "detailAttribute": {
                "naverShoppingSearchInfo": {"brandName": "브랜드"},
                "originAreaInfo": {"content": "대한민국"},
                "optionInfo": {
                    "optionCombinationGroupNames": {
                        "optionGroupName1": "색상",
                        "optionGroupName2": "사이즈",
                    },
                    "optionCombinations": [
                        {"optionName1": "검정", "optionName2": "95"},
                        {"optionName1": "검정", "optionName2": "100"},
                        {"optionName1": "흰색", "optionName2": "95"},
                    ],
                },
            },
        }
    }
    product = _extract_remote_product("smartstore", "321", raw)
    assert product["category"] == ""
    assert product["source_category_id"] == "50000641"
    assert product["options"] == [
        {"name": "색상", "values": ["검정", "흰색"]},
        {"name": "사이즈", "values": ["95", "100"]},
    ]
