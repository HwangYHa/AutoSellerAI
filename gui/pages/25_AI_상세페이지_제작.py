"""상품 원본 이미지 재수집 및 선택형 AI 썸네일/상세페이지 제작."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st

from app.config import get_settings
from app.db import Product, get_db
from app.media.ai_detail_page import build_detail_html, generate_detail_images
from app.media.thumbnail import generate_thumbnail
from app.suppliers.registry import get_adapter
from gui.korean_runtime import apply_korean_patch

apply_korean_patch()
st.set_page_config(page_title="AI 이미지 제작", page_icon="🖼️", layout="wide")

st.title("🖼️ 상품 이미지 · AI 썸네일 · 상세페이지 제작")
st.caption("공급처 원본 이미지를 기준으로 상품 외형을 유지하면서 대표 썸네일과 상세페이지 이미지를 선택적으로 제작합니다.")

with get_db() as db:
    products = db.query(Product).order_by(Product.id.desc()).limit(1000).all()
    rows = [
        {
            "id": p.id, "sku": p.sku, "name": p.name, "source": p.source,
            "source_id": p.source_id, "source_url": p.source_url,
            "category": p.category, "brand": p.brand, "origin": p.origin,
            "material": p.material, "sell_price": float(p.sell_price or 0),
            "images": json.loads(p.images or "[]"),
            "detail_images": json.loads(p.detail_images or "[]"),
            "detail_html": p.detail_html or "",
        }
        for p in products
    ]

if not rows:
    st.info("먼저 공급처 상품을 수집하거나 판매채널 상품을 동기화하세요.")
    st.stop()

selected = st.selectbox(
    "상품 선택",
    rows,
    format_func=lambda x: f"#{x['id']} · {x['name']} · {x['source']}",
)

st.markdown("### 1. 원본 이미지 확인")
a, b, c = st.columns(3)
a.metric("대표/기본 이미지", len(selected["images"]))
b.metric("상세 이미지", len(selected["detail_images"]))
c.metric("공급처", selected["source"] or "-")

all_original = selected["images"] + selected["detail_images"]
if all_original:
    cols = st.columns(4)
    for idx, url in enumerate(all_original[:20]):
        with cols[idx % 4]:
            st.image(url, caption=("기본" if idx < len(selected["images"]) else "상세"), use_container_width=True)
else:
    st.warning("현재 저장된 원본 이미지가 없습니다. 아래에서 공급처 원본 페이지를 다시 수집하세요.")

if st.button("🔄 공급처 이미지 태그 다시 수집", use_container_width=True):
    adapter = get_adapter(selected["source"])
    if not adapter:
        st.error(f"공급처 어댑터를 찾을 수 없습니다: {selected['source']}")
    else:
        with st.spinner("공급처 API와 원본 상품 HTML의 이미지 태그를 확인하고 있습니다..."):
            normalized = adapter.get_product(selected["source_id"])
        if not normalized:
            st.error("공급처에서 상품 상세정보를 가져오지 못했습니다.")
        else:
            with get_db() as db:
                p = db.query(Product).filter_by(id=selected["id"]).first()
                p.images = json.dumps(normalized.images, ensure_ascii=False)
                p.detail_images = json.dumps(normalized.detail_images, ensure_ascii=False)
                db.commit()
            st.success(f"이미지 수집 완료: 기본 {len(normalized.images)}장 / 상세 {len(normalized.detail_images)}장")
            st.rerun()

st.divider()
s = get_settings()
st.markdown("### 2. AI 상품 썸네일 제작")
mc1, mc2, mc3 = st.columns(3)
mc1.metric("이미지 모델", s.image_ai_model)
mc2.metric("썸네일 크기", s.image_thumbnail_size)
mc3.metric("품질", s.image_thumbnail_quality)
st.caption("이미지 endpoint에는 이미지 전용 모델만 사용합니다. 잘못된 텍스트 모델 설정은 런타임에서 gpt-image-2로 교정됩니다.")

if not s.image_ai_enabled:
    st.info("현재 IMAGE_AI_ENABLED=false 입니다. AI 제작이 필요할 때 true로 변경하세요.")
if not s.image_public_base_url:
    st.warning("IMAGE_PUBLIC_BASE_URL이 비어 있습니다. 생성 이미지는 로컬 미리보기까지 가능하지만 판매채널 대표이미지 URL로 바로 적용할 수는 없습니다.")

reference_candidates = selected["images"] or selected["detail_images"]
thumbnail_reference = st.selectbox(
    "썸네일 제품 외형 기준 이미지",
    [""] + reference_candidates,
    format_func=lambda u: "기준 이미지 없이 생성" if not u else u,
    key="thumbnail_reference",
)
style = st.selectbox(
    "썸네일 스타일",
    ["marketplace", "premium", "lifestyle"],
    format_func=lambda x: {"marketplace": "쇼핑몰 기본형", "premium": "프리미엄 카탈로그형", "lifestyle": "생활공간형"}[x],
)

payload = {
    "id": selected["id"], "sku": selected["sku"], "name": selected["name"],
    "category": selected["category"], "brand": selected["brand"],
    "origin": selected["origin"], "material": selected["material"],
    "sell_price": selected["sell_price"],
}

if st.button("🎯 AI 썸네일 생성", type="primary", use_container_width=True, disabled=not s.image_ai_enabled):
    try:
        with st.spinner("1:1 상품 썸네일을 제작하고 있습니다..."):
            thumb = generate_thumbnail(payload, reference_url=thumbnail_reference, style=style)
        st.session_state["generated_thumbnail"] = thumb
        st.success(f"썸네일을 생성했습니다. 사용 모델: {thumb.model}")
    except Exception as exc:
        st.error(str(exc))

thumb = st.session_state.get("generated_thumbnail")
if thumb:
    path = Path(thumb.local_path)
    if path.exists():
        st.image(str(path), caption=f"AI 썸네일 · {path.name}", width=520)
    if thumb.public_url:
        st.code(thumb.public_url)
        if st.button("✅ 이 이미지를 상품 대표이미지로 적용", use_container_width=True):
            current = [u for u in selected["images"] if u != thumb.public_url]
            merged = [thumb.public_url] + current
            with get_db() as db:
                p = db.query(Product).filter_by(id=selected["id"]).first()
                p.images = json.dumps(merged, ensure_ascii=False)
                db.commit()
            st.success("AI 썸네일을 첫 번째 대표이미지로 적용했습니다.")
            st.rerun()
    else:
        st.info("로컬 썸네일이 생성되었습니다. IMAGE_PUBLIC_BASE_URL/CDN 연결 후 판매채널 대표이미지로 적용할 수 있습니다.")

st.divider()
st.markdown("### 3. AI 상세페이지 이미지 제작")
if not s.image_public_base_url:
    st.warning("IMAGE_PUBLIC_BASE_URL이 비어 있습니다. AI 이미지는 로컬 미리보기까지 가능하지만 쿠팡/스마트스토어 업로드용 공개 URL로 자동 반영되지는 않습니다.")

reference = st.selectbox(
    "AI가 제품 외형을 참고할 기준 이미지",
    [""] + reference_candidates,
    format_func=lambda u: "기준 이미지 없이 생성" if not u else u,
    key="detail_reference",
)
count = st.slider("생성할 상세페이지 섹션 수", min_value=1, max_value=5, value=min(max(s.image_ai_detail_count, 1), 5))
confirm = st.checkbox("원본 상품과 다른 기능·성능을 임의로 만들지 않도록 reference 기반으로 제작합니다.", value=bool(reference))

if st.button("✨ AI 상세페이지 이미지 생성", type="primary", use_container_width=True, disabled=not s.image_ai_enabled):
    if not reference and not confirm:
        st.error("제품 정확성을 위해 기준 이미지를 선택하거나 생성 조건을 확인하세요.")
    else:
        try:
            with st.spinner("AI 상세페이지 이미지를 제작하고 있습니다..."):
                generated = generate_detail_images(payload, count=count, reference_url=reference)
            st.session_state["generated_detail_images"] = generated
            st.success(f"AI 상세페이지 이미지 {len(generated)}장을 생성했습니다. 사용 모델: {s.image_ai_model}")
        except Exception as exc:
            st.error(str(exc))

created = st.session_state.get("generated_detail_images") or []
if created:
    st.markdown("#### 생성 결과")
    for item in created:
        path = Path(item.local_path)
        if path.exists():
            st.image(str(path), caption=f"{item.role} · {path.name}", use_container_width=True)
        if item.public_url:
            st.code(item.public_url)

    public_urls = [x.public_url for x in created if x.public_url]
    if public_urls:
        if st.button("✅ 공개 URL 상세이미지로 상품에 적용", use_container_width=True):
            merged = list(dict.fromkeys(selected["detail_images"] + public_urls))
            html = build_detail_html(selected, merged)
            with get_db() as db:
                p = db.query(Product).filter_by(id=selected["id"]).first()
                p.detail_images = json.dumps(merged, ensure_ascii=False)
                if html:
                    p.detail_html = html
                db.commit()
            st.success("AI 상세이미지 공개 URL을 상품 상세페이지에 적용했습니다.")
            st.rerun()
    else:
        st.info("현재 결과는 로컬 파일입니다. IMAGE_PUBLIC_BASE_URL/CDN 연결 후에만 플랫폼 업로드용 상세이미지로 자동 반영합니다.")

with st.expander("이미지 제작 규칙 보기"):
    st.markdown(
        """
- 공급처 API가 주는 `images`, `detail_images`를 가장 먼저 사용합니다.
- 원본 데이터의 HTML에서 `img src`, `data-src`, `data-original`, `data-lazy-src`, `srcset`을 추가 수집합니다.
- 상세설명 영역으로 판단되는 컨테이너 내부 이미지는 상세이미지로 분류합니다.
- 단건 상품 조회 시 `IMAGE_SOURCE_PAGE_FETCH=true`이면 실제 상품 페이지 HTML도 한 번 확인합니다.
- AI 이미지는 자동 생성하지 않으며 `IMAGE_AI_ENABLED=true`이고 사용자가 생성 버튼을 눌렀을 때만 제작합니다.
- 이미지 생성 모델은 `gpt-image-2`, `gpt-image-1.5`, `gpt-image-1-mini`만 허용합니다.
- `gpt-5.6-luna` 같은 텍스트 모델이 IMAGE_AI_MODEL에 들어가면 `gpt-image-2`로 자동 교정합니다.
- 썸네일은 1:1 정사각형으로 제작하며 상품을 화면 중심에 크게 배치하고 가격/할인/가짜 스펙 텍스트를 생성하지 않습니다.
- 원본 제품 사진을 reference로 사용해 실제 상품 외형이 바뀌는 것을 최소화합니다.
        """
    )
