"""Structured adult body-profile presets for Stable Diffusion."""
from __future__ import annotations

import streamlit as st

from app.image_studio.body_profile_reference import extended_reference
from app.image_studio.body_profiles import (
    BODY_PROFILE_CONTROL_DEFAULTS,
    BODY_PROFILE_MAP,
    BODY_PROFILE_META,
    BUST_VOLUME_MAP,
    LEG_PROPORTION_MAP,
    MUSCLE_TONE_MAP,
    RIBCAGE_MAP,
)
from app.image_studio.mappings import (
    BACKGROUND_MAP, BODY_FRAME_MAP, CHEST_PROPORTION_MAP, HEIGHT_MAP,
    OUTFIT_MAP, POSE_MAP, SHOULDER_MAP, SHOT_MAP, WAIST_HIP_MAP,
)
from app.image_studio.prompt_builder import build_prompt
from app.image_studio.schemas import HumanImageRequest
from app.image_studio.sd_webui_client import StableDiffusionWebUIClient
from app.image_studio.service import create_generation, get_image_queue_status
from gui.korean_runtime import apply_korean_patch


apply_korean_patch()
st.set_page_config(page_title="AI 체형 프리셋 | AutoSellerAI", page_icon="🧍", layout="wide")
st.title("🧍 AI 인물 체형 프리셋")
st.caption("매우 슬림 · 슬림 · 슬림 글래머 · 균형형 · 볼륨형 · 운동형을 Stable Diffusion에 맞는 실사형 자연어로 변환합니다.")
st.info("키·체중·BMI·체지방률·밑가슴·브라 사이즈는 제공된 분류표를 보존하기 위한 참고 메타데이터입니다. 정확한 생성 수치나 건강 기준으로 사용하지 않습니다. 모든 기본 생성은 성인·완전 착의 상업/라이프스타일 이미지입니다.")


def _caps() -> dict:
    try:
        return StableDiffusionWebUIClient().capabilities().model_dump()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _apply_profile_defaults(profile_name: str) -> None:
    defaults = BODY_PROFILE_CONTROL_DEFAULTS[profile_name]
    keys = {
        "body_frame": "bp_body_frame", "height_impression": "bp_height",
        "shoulder": "bp_shoulder", "ribcage": "bp_ribcage",
        "bust_volume": "bp_bust", "chest_proportion": "bp_chest",
        "waist_hip": "bp_waist_hip", "muscle_tone": "bp_muscle",
        "leg_proportion": "bp_leg",
    }
    for field, key in keys.items():
        st.session_state[key] = defaults[field]


caps = _caps()
try:
    queue = get_image_queue_status()
except Exception as exc:
    queue = {"ok": False, "workers": 0, "error": str(exc)}
ready = bool(caps.get("ok") and queue.get("ok") and int(queue.get("workers") or 0) > 0)

s1, s2, s3 = st.columns(3)
s1.metric("Stable Diffusion", "연결됨" if caps.get("ok") else "오프라인")
s2.metric("Image Worker", f"{int(queue.get('workers') or 0)}개")
s3.metric("생성 준비", "완료" if ready else "확인 필요")

profile = st.selectbox("대표 체형", list(BODY_PROFILE_MAP.keys()), index=3, key="bp_profile")
meta = BODY_PROFILE_META[profile]
if "bp_body_frame" not in st.session_state:
    _apply_profile_defaults(profile)

p_apply, p_hint = st.columns([1.2, 3.8])
with p_apply:
    if st.button("⚡ 이 프로필 권장값 적용", use_container_width=True):
        _apply_profile_defaults(profile)
        st.rerun()
with p_hint:
    st.caption("프로필을 바꾼 뒤 이 버튼을 누르면 흉곽·상체 볼륨·허리/힙·근육·다리 비율까지 권장 조합으로 맞춰집니다. 이후 항목별 수정도 가능합니다.")

st.markdown("### 참고 프로필")
a, b, c, d = st.columns(4)
a.metric("키 참고", meta["height_reference"])
b.metric("체중 참고", meta["weight_reference"])
c.metric("BMI 참고", meta["bmi_reference"])
d.metric("체지방 인상 참고", meta["body_fat_visual_reference"])
st.write(f"**전체 인상:** {meta['overall_impression']}")
st.write(f"**의상 핏:** {meta['clothing_fit']}")
st.caption(f"어깨 {meta['shoulder']} · 흉곽 {meta['ribcage']} · 밑가슴 참고 {meta['underbust_reference']} · WHR 참고 {meta['whr_reference']} · 다리 비율 참고 {meta['leg_ratio_reference']} · SD 난이도 {meta['sd_difficulty']}")
if meta.get("bra_example"):
    st.caption(f"브라 사이즈 예시: {meta['bra_example']} · 실제 인물/생성 결과의 정확한 치수를 의미하지 않습니다.")

with st.expander("📋 누락 없이 보존된 상세 참고표", expanded=False):
    ext = extended_reference(profile)
    labels = {
        "bust_projection": "상체 측면 돌출 인상", "upper_lower_volume": "윗/아랫볼륨 분포",
        "natural_shape": "자연스러운 형태", "waist_curve": "허리 굴곡",
        "muscle_abdomen": "근육량/복부", "clothed_impression": "옷 입었을 때",
        "ribcage_ratio": "흉곽 대비 실루엣", "side_projection": "측면 곡선",
        "upper_chest_drape": "윗부분/중력감", "tshirt_fit": "티셔츠 착용 시",
        "knit_fit": "니트 착용 시", "dress_fit": "원피스 착용 시",
        "visual_emphasis_factors": "상대적으로 커 보이는 요인", "sd_phrase_reference": "SD 자연어 참고",
    }
    for key, label in labels.items():
        if ext.get(key):
            st.markdown(f"**{label}** · {ext[key]}")
    st.caption("위 항목은 참고용 분류 데이터입니다. 생성 프롬프트에는 현실적인 해부학·의상 드레이프를 유지하는 범위의 질적 표현만 반영합니다.")

st.divider()
st.markdown("### 생성용 세부 조정")

c1, c2, c3 = st.columns(3)
with c1:
    body_frame = st.selectbox("전체 체형", list(BODY_FRAME_MAP), key="bp_body_frame")
    height_impression = st.selectbox("키 인상", list(HEIGHT_MAP), key="bp_height")
    shoulder = st.selectbox("어깨선", list(SHOULDER_MAP), key="bp_shoulder")
with c2:
    ribcage = st.selectbox("흉곽", list(RIBCAGE_MAP), key="bp_ribcage")
    bust_volume = st.selectbox("상체 볼륨", list(BUST_VOLUME_MAP), key="bp_bust")
    chest_proportion = st.selectbox("상체 비율", list(CHEST_PROPORTION_MAP), key="bp_chest")
with c3:
    waist_hip = st.selectbox("허리·힙 실루엣", list(WAIST_HIP_MAP), key="bp_waist_hip")
    muscle_tone = st.selectbox("근육·복부 톤", list(MUSCLE_TONE_MAP), key="bp_muscle")
    leg_proportion = st.selectbox("다리 비율 인상", list(LEG_PROPORTION_MAP), key="bp_leg")

st.markdown("### 촬영 설정")
p1, p2, p3 = st.columns(3)
with p1:
    outfit = st.selectbox("의상", list(OUTFIT_MAP), index=list(OUTFIT_MAP).index("데일리 캐주얼"))
    pose = st.selectbox("포즈", list(POSE_MAP), index=list(POSE_MAP).index("자연스럽게 서기"))
with p2:
    shot = st.selectbox("구도", list(SHOT_MAP), index=list(SHOT_MAP).index("전신"))
    background = st.selectbox("배경", list(BACKGROUND_MAP), index=list(BACKGROUND_MAP).index("화이트 스튜디오"))
with p3:
    batch = st.slider("생성 장수", 1, 4, 1)
    seed = st.number_input("Seed (-1=랜덤)", min_value=-1, max_value=2147483647, value=-1, step=1)

request = HumanImageRequest(
    preset="쇼핑몰 모델컷",
    body_profile=profile,
    body_frame=body_frame,
    height_impression=height_impression,
    shoulder=shoulder,
    waist_hip=waist_hip,
    chest_proportion=chest_proportion,
    ribcage=ribcage,
    bust_volume=bust_volume,
    muscle_tone=muscle_tone,
    leg_proportion=leg_proportion,
    outfit=outfit,
    pose=pose,
    shot=shot,
    background=background,
    batch_size=batch,
    seed=int(seed),
)
bundle = build_prompt(request)

with st.expander("최종 체형 프롬프트 확인"):
    st.text_area("Positive Prompt", bundle.positive, height=220, disabled=True)
    st.text_area("Negative Prompt", bundle.negative, height=130, disabled=True)
    st.caption("숫자형 참고치가 프롬프트에 직접 들어가지 않는 것이 정상입니다.")

if not ready:
    st.warning("Stable Diffusion WebUI와 image-worker가 모두 정상이어야 생성할 수 있습니다.")

if st.button("✨ 이 체형으로 이미지 생성", type="primary", use_container_width=True, disabled=not ready):
    try:
        row = create_generation(request)
        st.success(f"Generation #{row.id} 등록 완료. AI 인물 이미지 스튜디오의 생성 이력에서 결과와 Seed를 재사용할 수 있습니다.")
    except Exception as exc:
        st.error(str(exc))

st.page_link("pages/13_AI_인물_이미지_스튜디오.py", label="🎨 전체 얼굴·헤어·의상·촬영 설정으로 이동")
