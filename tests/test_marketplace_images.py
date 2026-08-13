from app.media.marketplace_images import (
    extract_coupang_product_images,
    normalize_image_url,
)


def test_coupang_relative_cdn_path_becomes_browser_url():
    value = "vendor_inventory/images/2019/01/09/18/a/sample.jpg"
    assert normalize_image_url(value, platform="coupang") == (
        "https://image11.coupangcdn.com/image/" + value
    )


def test_coupang_http_cdn_url_is_upgraded_to_https():
    value = "http://image11.coupangcdn.com/image/product/a.jpg"
    assert normalize_image_url(value, platform="coupang") == (
        "https://image11.coupangcdn.com/image/product/a.jpg"
    )


def test_bare_vendor_filename_is_not_rendered_as_image():
    assert normalize_image_url("coupang_image_123.jpg", platform="coupang") == ""


def test_coupang_representation_and_detail_are_split():
    detail = {
        "items": [{
            "images": [
                {
                    "imageOrder": 0,
                    "imageType": "REPRESENTATION",
                    "cdnPath": "vendor_inventory/images/main.jpg",
                    "vendorPath": "main.jpg",
                },
                {
                    "imageOrder": 1,
                    "imageType": "DETAIL",
                    "vendorPath": "http://image11.coupangcdn.com/image/product/detail.jpg",
                },
            ],
            "contents": [{
                "contentDetails": [{
                    "content": '<img src="http://img1a.coupangcdn.com/image/vendor_inventory/content.jpg">'
                }]
            }],
        }]
    }
    reps, details = extract_coupang_product_images(detail)
    assert reps == ["https://image11.coupangcdn.com/image/vendor_inventory/images/main.jpg"]
    assert "https://image11.coupangcdn.com/image/product/detail.jpg" in details
    assert "https://img1a.coupangcdn.com/image/vendor_inventory/content.jpg" in details
