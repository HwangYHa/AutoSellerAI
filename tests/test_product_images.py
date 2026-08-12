from app.media.product_images import extract_images_from_html
from app.media.ai_detail_page import build_detail_prompts


def test_extract_product_and_detail_images_from_html_tags():
    html = """
    <html><head><meta property="og:image" content="/main.jpg"></head>
    <body>
      <img data-src="/gallery/a.webp" />
      <div id="product-detail">
        <img src="/detail/01.jpg" />
        <img data-original="//cdn.example.com/detail/02.png" />
        <source srcset="/detail/03.webp 1x, /detail/03@2x.webp 2x" />
      </div>
    </body></html>
    """
    result = extract_images_from_html(html, "https://shop.example.com/item/1")
    assert "https://shop.example.com/main.jpg" in result.images
    assert "https://shop.example.com/gallery/a.webp" in result.images
    assert "https://shop.example.com/detail/01.jpg" in result.detail_images
    assert "https://cdn.example.com/detail/02.png" in result.detail_images
    assert "https://shop.example.com/detail/03.webp" in result.detail_images


def test_ai_detail_prompts_use_only_known_product_facts():
    product = {
        "name": "무선 차량용 청소기",
        "category": "자동차용품",
        "brand": "테스트브랜드",
        "origin": "한국",
        "material": "ABS",
    }
    prompts = build_detail_prompts(product, 3)
    assert len(prompts) == 3
    joined = " ".join(p for _, p in prompts)
    assert "무선 차량용 청소기" in joined
    assert "테스트브랜드" in joined
    assert "한국" in joined
    assert "임의로 추가하지 말 것" in joined
