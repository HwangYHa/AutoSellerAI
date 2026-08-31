"""Korean UI labels -> model-agnostic Stable Diffusion prompt fragments.

Keep these fragments descriptive and photographic.  They deliberately avoid
checkpoint-specific trigger tokens so the same UI can work with SD 1.5, SDXL and
compatible photoreal checkpoints.  Character age choices are adult-only.
"""
from __future__ import annotations

from typing import Mapping


GENDER_MAP: Mapping[str, str] = {
    "여성": "adult Korean woman",
    "남성": "adult Korean man",
}

AGE_MAP: Mapping[str, str] = {
    "20대 초반": "in their early twenties",
    "20대 중반": "in their mid twenties",
    "20대 후반": "in their late twenties",
    "30대 초반": "in their early thirties",
    "30대 중반": "in their mid thirties",
    "30대 후반": "in their late thirties",
    "40대": "in their forties",
}

HAIR_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 단발": "natural short bob haircut",
    "턱선 단발": "chin-length bob haircut",
    "긴 생머리": "long straight hair",
    "긴 웨이브": "long soft wavy hair",
    "레이어드컷": "soft layered haircut",
    "포니테일": "neat natural ponytail",
    "로우번": "clean low bun hairstyle",
    "숏컷": "clean short haircut",
    "가르마 헤어": "neat side-parted hair",
    "쉼표 머리": "soft comma hairstyle",
}

HAIR_COLOR_MAP: Mapping[str, str] = {
    "검정": "natural black hair",
    "다크브라운": "dark brown hair",
    "브라운": "natural brown hair",
    "애쉬브라운": "soft ash brown hair",
    "밝은 브라운": "light warm brown hair",
}

FACE_SHAPE_MAP: Mapping[str, str] = {
    "계란형": "balanced oval face",
    "갸름한형": "slender softly tapered face",
    "둥근형": "soft round face",
    "각진형": "subtly defined angular face",
    "하트형": "soft heart-shaped face",
}

EYE_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 눈매": "natural balanced eyes",
    "또렷한 눈매": "clear defined eyes",
    "부드러운 눈매": "soft gentle eyes",
    "고양이상": "slightly upturned cat-like eyes",
    "강아지상": "warm softly rounded eyes",
}

NOSE_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 코": "natural proportional nose",
    "오똑한 코": "clean defined nose bridge",
    "부드러운 코선": "soft natural nose profile",
}

LIP_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 입술": "natural proportional lips",
    "도톰한 입술": "soft naturally full lips",
    "얇고 정돈된 입술": "neat subtly thin lips",
}

SKIN_TONE_MAP: Mapping[str, str] = {
    "밝은 뉴트럴": "light neutral Korean skin tone",
    "내추럴": "natural Korean skin tone",
    "웜": "warm healthy Korean skin tone",
    "살짝 태닝": "lightly sun-kissed Korean skin tone",
}

EXPRESSION_MAP: Mapping[str, str] = {
    "무표정/차분": "calm relaxed expression",
    "은은한 미소": "subtle natural smile",
    "밝은 미소": "bright friendly smile",
    "자신감 있는 표정": "confident composed expression",
    "장난스러운 표정": "playful friendly expression",
}

BODY_FRAME_MAP: Mapping[str, str] = {
    "아담한 체형": "petite naturally proportioned adult body",
    "슬림": "slim naturally proportioned adult body",
    "균형형": "balanced natural adult body proportions",
    "자연스러운 볼륨형": "naturally curvy balanced adult silhouette",
    "애슬레틱": "fit athletic adult physique with natural proportions",
    "탄탄한 체형": "toned healthy adult physique",
}

HEIGHT_MAP: Mapping[str, str] = {
    "아담한 인상": "petite height impression",
    "평균적인 인상": "average height impression",
    "큰 키 인상": "tall elegant height impression",
}

SHOULDER_MAP: Mapping[str, str] = {
    "좁고 부드러운 어깨": "soft narrow shoulder line",
    "균형 잡힌 어깨": "balanced shoulder proportions",
    "곧고 탄탄한 어깨": "straight toned shoulder line",
}

WAIST_HIP_MAP: Mapping[str, str] = {
    "일자형": "straight natural waist and hip silhouette",
    "균형형": "balanced natural waist and hip proportions",
    "곡선형": "gently curved natural waist and hip silhouette",
}

CHEST_PROPORTION_MAP: Mapping[str, str] = {
    "자연스러운 비율": "natural proportional torso",
    "슬림한 상체": "slender upper-body proportions",
    "자연스러운 볼륨감": "naturally fuller but realistic upper-body proportions",
}

OUTFIT_MAP: Mapping[str, str] = {
    "데일리 캐주얼": "wearing a tasteful everyday casual outfit",
    "캐주얼 니트": "wearing a soft knit top with clean casual bottoms",
    "오피스룩": "wearing a polished office blouse and tailored slacks",
    "미니멀 셋업": "wearing a minimalist coordinated outfit",
    "세련된 원피스": "wearing an elegant contemporary dress",
    "스트릿 캐주얼": "wearing modern tasteful streetwear",
    "스포티 캐주얼": "wearing clean modern athleisure",
    "여름 데일리룩": "wearing a light tasteful summer outfit",
    "겨울 데일리룩": "wearing layered tasteful winter casual clothing",
    "남성 미니멀룩": "wearing a clean minimalist menswear outfit",
    "남성 오피스룩": "wearing a refined shirt and tailored trousers",
}

OUTFIT_COLOR_MAP: Mapping[str, str] = {
    "자동/자연스럽게": "harmonious neutral clothing colors",
    "블랙": "predominantly black outfit",
    "화이트": "predominantly white outfit",
    "아이보리/베이지": "ivory and beige color palette",
    "브라운": "warm brown color palette",
    "그레이": "clean gray color palette",
    "네이비": "refined navy color palette",
    "파스텔": "soft tasteful pastel color palette",
}

MOOD_MAP: Mapping[str, str] = {
    "자연스러움": "natural effortless atmosphere",
    "청순/맑음": "clean fresh gentle atmosphere",
    "세련됨": "refined stylish atmosphere",
    "도회적": "urban sophisticated atmosphere",
    "귀여움": "bright charming approachable atmosphere",
    "럭셔리": "understated luxurious elegant atmosphere",
    "시크": "cool chic composed atmosphere",
    "따뜻함": "warm cozy approachable atmosphere",
}

PERSONALITY_MAP: Mapping[str, str] = {
    "밝고 친근함": "friendly open body language and warm presence",
    "차분하고 지적": "calm intelligent composed presence",
    "자신감 있음": "confident poised body language",
    "사랑스럽고 부드러움": "gentle approachable body language",
    "활발하고 에너지 있음": "energetic upbeat natural body language",
    "시크하고 절제됨": "restrained chic confident presence",
}

POSE_MAP: Mapping[str, str] = {
    "자연스럽게 서기": "natural relaxed standing pose",
    "카메라 바라보기": "looking naturally toward the camera",
    "살짝 측면": "subtle three-quarter body angle",
    "걷는 순간": "natural candid walking moment",
    "의자에 앉기": "natural seated pose with relaxed posture",
    "상품을 들고 있기": "naturally holding the featured product with anatomically correct hands",
}

SHOT_MAP: Mapping[str, str] = {
    "얼굴 클로즈업": "close-up portrait, face and shoulders clearly framed",
    "상반신": "upper-body portrait, torso clearly visible",
    "허벅지 위": "three-quarter portrait framed above the knees",
    "전신": "full-body fashion photograph, entire body and feet visible",
}

BACKGROUND_MAP: Mapping[str, str] = {
    "화이트 스튜디오": "clean white photography studio background",
    "감성 카페": "tasteful contemporary cafe interior",
    "미니멀 갤러리": "minimal modern art gallery interior",
    "모던 오피스": "modern refined office interior",
    "도심 스트릿": "clean contemporary Korean urban street",
    "편안한 집": "tasteful cozy modern apartment interior",
    "호텔 라운지": "understated upscale hotel lounge",
    "한강/공원": "clean urban riverside park setting",
    "해변": "bright natural beach setting",
}

LIGHTING_MAP: Mapping[str, str] = {
    "부드러운 자연광": "soft diffused natural daylight, realistic skin illumination",
    "창가 자연광": "soft window daylight with realistic directional shadows",
    "밝은 스튜디오": "clean softbox studio lighting with balanced exposure",
    "골든아워": "warm golden-hour natural light with controlled highlights",
    "흐린날 소프트광": "soft overcast daylight with even skin tones",
    "시네마틱": "controlled cinematic key light with realistic fill light",
}

DOF_MAP: Mapping[str, str] = {
    "배경까지 선명": "deep depth of field, subject and background both clearly resolved",
    "자연스러운 심도": "natural moderate depth of field, subject clearly focused",
    "인물 중심": "gentle subject separation with a recognizable background",
}

CAMERA_MAP: Mapping[str, str] = {
    "자연스러운 스마트폰 사진": "high-end smartphone lifestyle photography, natural perspective",
    "35mm 환경 인물": "35mm environmental portrait photography, natural perspective",
    "50mm 자연 인물": "50mm portrait photography, realistic perspective",
    "85mm 패션 인물": "85mm fashion portrait photography, flattering realistic perspective",
}

PRESETS = {
    "실사 인플루언서": {
        "shot": "상반신",
        "background": "감성 카페",
        "lighting": "창가 자연광",
        "camera": "50mm 자연 인물",
        "dof": "자연스러운 심도",
        "steps": 30,
        "cfg_scale": 6.0,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "쇼핑몰 모델컷": {
        "shot": "전신",
        "background": "화이트 스튜디오",
        "lighting": "밝은 스튜디오",
        "camera": "50mm 자연 인물",
        "dof": "배경까지 선명",
        "steps": 32,
        "cfg_scale": 6.0,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "Threads/SNS 세로컷": {
        "shot": "허벅지 위",
        "background": "도심 스트릿",
        "lighting": "부드러운 자연광",
        "camera": "35mm 환경 인물",
        "dof": "자연스러운 심도",
        "steps": 28,
        "cfg_scale": 5.5,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "감성 프로필": {
        "shot": "얼굴 클로즈업",
        "background": "미니멀 갤러리",
        "lighting": "창가 자연광",
        "camera": "85mm 패션 인물",
        "dof": "인물 중심",
        "steps": 30,
        "cfg_scale": 5.5,
        "width": 832,
        "height": 1216,
        "hires": True,
    },
    "오피스 프로필": {
        "shot": "상반신",
        "background": "모던 오피스",
        "lighting": "밝은 스튜디오",
        "camera": "50mm 자연 인물",
        "dof": "배경까지 선명",
        "steps": 30,
        "cfg_scale": 6.0,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
}


def option_keys(mapping: Mapping[str, str]) -> list[str]:
    return list(mapping.keys())


__all__ = [name for name in globals() if name.endswith("_MAP")] + ["PRESETS", "option_keys"]
