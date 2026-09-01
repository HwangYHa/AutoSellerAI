"""Adult body-profile presets for the Stable Diffusion human studio.

The user-facing reference table contains approximate height/weight/BMI/body-fat and
clothing-fit notes. Those values are retained as descriptive UI metadata only; they
are not injected verbatim into Stable Diffusion prompts because text-to-image models
cannot reliably honor anthropometric measurements and numeric over-constraint tends
to increase anatomy/garment artifacts.

All profiles are adult-only and generate fully clothed commercial/lifestyle imagery.
"""
from __future__ import annotations

from typing import Any, Mapping


BODY_PROFILE_MAP: Mapping[str, str] = {
    "매우 슬림": (
        "very slim delicate adult feminine silhouette, petite narrow ribcage, low overall body volume, "
        "subtle upper-torso volume, relatively straight waist line, lean natural legs, realistic healthy anatomy"
    ),
    "슬림": (
        "slim clean adult feminine silhouette, narrow ribcage, modest natural upper-torso volume, "
        "gently defined waist, slightly long-looking legs, minimal excess body softness, realistic anatomy"
    ),
    "슬림 글래머": (
        "slim adult feminine frame with clearly defined waist-to-hip contrast, narrow ribcage, "
        "moderate-to-full natural upper-torso volume, softly rounded curves concentrated around torso and hips, "
        "realistic non-exaggerated anatomy"
    ),
    "균형형": (
        "balanced adult feminine proportions, moderate ribcage, natural medium upper-torso volume, "
        "softly defined waist and hips, slightly long-looking legs, even distribution of body softness, realistic anatomy"
    ),
    "볼륨형": (
        "fuller naturally curvy adult feminine silhouette, broader ribcage, full natural upper-torso volume, "
        "clear waist-to-hip curve, soft body contours with realistic gravity and fabric drape, non-exaggerated anatomy"
    ),
    "운동형": (
        "fit athletic adult feminine silhouette, straight toned shoulders, moderate-to-broad ribcage, "
        "firm natural upper-torso proportions, defined core, lifted athletic hip line, lightly visible muscle tone, "
        "realistic anatomy"
    ),
}

RIBCAGE_MAP: Mapping[str, str] = {
    "자동/프로필 기준": "",
    "매우 좁음": "very narrow petite ribcage and compact upper torso",
    "좁음": "narrow ribcage with slender upper-torso width",
    "보통": "moderate naturally proportioned ribcage",
    "넓은 편": "slightly broad naturally proportioned ribcage",
    "보통~넓고 탄탄함": "moderate-to-broad toned athletic ribcage",
}

BUST_VOLUME_MAP: Mapping[str, str] = {
    "자동/프로필 기준": "",
    "아주 작음": "very subtle natural bust volume relative to the ribcage",
    "작음~보통": "small-to-moderate natural bust volume with gentle contour",
    "보통": "moderate natural bust volume balanced to the frame",
    "보통~큰 편": "moderate-to-full natural bust volume with realistic fabric drape",
    "큼": "full natural bust volume with realistic gravity and clothing fit, without exaggeration",
    "운동형 보통": "moderate firm athletic upper-torso volume supported by toned musculature",
}

MUSCLE_TONE_MAP: Mapping[str, str] = {
    "자동/프로필 기준": "",
    "매우 적음·납작함": "very low visible muscle definition, flat relaxed abdomen",
    "적음·군살 적음": "light muscle definition with a clean flat silhouette",
    "보통·부드러움": "moderate natural muscle tone with a soft flat abdomen",
    "보통·자연스러움": "moderate natural muscle tone and relaxed body lines",
    "보통·부드러운 곡선": "moderate muscle tone under softer natural body contours",
    "높음·탄탄한 코어": "clearly toned athletic core with subtle natural abdominal definition",
}

LEG_PROPORTION_MAP: Mapping[str, str] = {
    "자동/프로필 기준": "",
    "일반적": "natural average leg-to-body visual proportion",
    "약간 긴 편": "slightly long-looking legs with realistic proportions",
    "긴 편": "long-looking legs with balanced realistic body proportions",
}


BODY_FRAME_PROFILE_ALIAS: Mapping[str, str] = {
    "매우 슬림": "매우 슬림",
    "아담한 체형": "매우 슬림",
    "슬림": "슬림",
    "슬림 균형형": "슬림",
    "슬림 글래머": "슬림 글래머",
    "균형형": "균형형",
    "자연스러운 볼륨형": "볼륨형",
    "볼륨형": "볼륨형",
    "애슬레틱": "운동형",
    "탄탄한 체형": "운동형",
    "러너형": "운동형",
    "근육형": "운동형",
}


BODY_PROFILE_CONTROL_DEFAULTS: Mapping[str, Mapping[str, str]] = {
    "매우 슬림": {
        "body_frame": "매우 슬림", "height_impression": "평균적인 인상",
        "shoulder": "좁고 부드러운 어깨", "waist_hip": "일자형",
        "chest_proportion": "매우 슬림한 상체", "ribcage": "매우 좁음",
        "bust_volume": "아주 작음", "muscle_tone": "매우 적음·납작함", "leg_proportion": "일반적",
    },
    "슬림": {
        "body_frame": "슬림", "height_impression": "평균적인 인상",
        "shoulder": "균형 잡힌 어깨", "waist_hip": "허리선 강조형",
        "chest_proportion": "슬림한 상체", "ribcage": "좁음",
        "bust_volume": "작음~보통", "muscle_tone": "적음·군살 적음", "leg_proportion": "약간 긴 편",
    },
    "슬림 글래머": {
        "body_frame": "슬림 글래머", "height_impression": "평균적인 인상",
        "shoulder": "균형 잡힌 어깨", "waist_hip": "모래시계형",
        "chest_proportion": "자연스러운 볼륨감", "ribcage": "좁음",
        "bust_volume": "보통~큰 편", "muscle_tone": "보통·부드러움", "leg_proportion": "약간 긴 편",
    },
    "균형형": {
        "body_frame": "균형형", "height_impression": "평균적인 인상",
        "shoulder": "살짝 넓은 어깨", "waist_hip": "곡선형",
        "chest_proportion": "자연스러운 비율", "ribcage": "보통",
        "bust_volume": "보통", "muscle_tone": "보통·자연스러움", "leg_proportion": "긴 편",
    },
    "볼륨형": {
        "body_frame": "볼륨형", "height_impression": "평균적인 인상",
        "shoulder": "균형 잡힌 어깨", "waist_hip": "모래시계형",
        "chest_proportion": "자연스러운 볼륨감", "ribcage": "넓은 편",
        "bust_volume": "큼", "muscle_tone": "보통·부드러운 곡선", "leg_proportion": "일반적",
    },
    "운동형": {
        "body_frame": "애슬레틱", "height_impression": "평균적인 인상",
        "shoulder": "곧고 탄탄한 어깨", "waist_hip": "애슬레틱 힙라인",
        "chest_proportion": "탄탄한 상체", "ribcage": "보통~넓고 탄탄함",
        "bust_volume": "운동형 보통", "muscle_tone": "높음·탄탄한 코어", "leg_proportion": "약간 긴 편",
    },
}


BODY_PROFILE_META: Mapping[str, Mapping[str, Any]] = {
    "매우 슬림": {
        "overall_impression": "가녀리고 매우 슬림한 인상", "height_reference": "160~168cm",
        "weight_reference": "43~46kg", "bmi_reference": "16.5~17.5", "body_fat_visual_reference": "17~19% 느낌",
        "shoulder": "좁고 둥근 편", "ribcage": "매우 좁음 (petite)", "underbust_reference": "65cm",
        "bust_volume": "아주 작음", "whr_reference": "약 0.80", "leg_ratio_reference": "약 45%",
        "muscle": "매우 적음, 납작한 실루엣", "clothing_fit": "여리여리한 핏, 오버핏과 잘 어울림",
        "sd_difficulty": "쉬움", "bra_example": "70A",
    },
    "슬림": {
        "overall_impression": "깔끔하고 옷태가 잘 받는 슬림형", "height_reference": "162~168cm",
        "weight_reference": "47~50kg", "bmi_reference": "17.5~18.5", "body_fat_visual_reference": "20~22% 느낌",
        "shoulder": "직각에 가까운 보통 폭", "ribcage": "좁음 (narrow)", "underbust_reference": "65~70cm",
        "bust_volume": "작음~보통", "whr_reference": "약 0.75", "leg_ratio_reference": "약 46%",
        "muscle": "적음, 군살이 적은 평면 실루엣", "clothing_fit": "핏감이 깔끔하고 몸에 맞는 옷이 안정적",
        "sd_difficulty": "쉬움", "bra_example": "70B",
    },
    "슬림 글래머": {
        "overall_impression": "허리가 얇고 상·하체 굴곡 대비가 뚜렷함", "height_reference": "162~167cm",
        "weight_reference": "49~53kg", "bmi_reference": "18.5~19.5", "body_fat_visual_reference": "22~24% 느낌",
        "shoulder": "보통, 골반과 균형", "ribcage": "좁음 (narrow)", "underbust_reference": "70cm",
        "bust_volume": "보통~큰 편", "whr_reference": "약 0.68~0.70", "leg_ratio_reference": "약 46%",
        "muscle": "보통, 부드러운 평면", "clothing_fit": "허리선이 잡힌 의상에서 대비감이 큼",
        "sd_difficulty": "중간 · 과장 방지를 위한 세밀한 프롬프트 필요", "bra_example": "70C",
    },
    "균형형": {
        "overall_impression": "단정하고 전체 비율이 고른 인상", "height_reference": "164~170cm",
        "weight_reference": "51~55kg", "bmi_reference": "19.0~20.5", "body_fat_visual_reference": "23~25% 느낌",
        "shoulder": "보통~약간 넓음", "ribcage": "보통 (moderate)", "underbust_reference": "70~75cm",
        "bust_volume": "보통", "whr_reference": "약 0.73~0.75", "leg_ratio_reference": "약 47%",
        "muscle": "보통, 자연스러운 라인", "clothing_fit": "기성복이 가장 안정적으로 맞는 편",
        "sd_difficulty": "가장 쉬움", "bra_example": "70D",
    },
    "볼륨형": {
        "overall_impression": "굴곡이 크고 부드러운 성인 체형 인상", "height_reference": "160~166cm",
        "weight_reference": "54~59kg", "bmi_reference": "20.5~22.0", "body_fat_visual_reference": "26~29% 느낌",
        "shoulder": "보통", "ribcage": "넓은 편 (broad)", "underbust_reference": "75~80cm",
        "bust_volume": "큼", "whr_reference": "약 0.70~0.72", "leg_ratio_reference": "약 45%",
        "muscle": "보통, 부드러운 곡선", "clothing_fit": "상의 볼륨과 원단 드레이프가 크게 드러날 수 있음",
        "sd_difficulty": "중간 · 과장되기 쉬워 realistic/non-exaggerated 제약 필요", "bra_example": "70E",
    },
    "운동형": {
        "overall_impression": "탄탄하고 건강한 운동형 인상", "height_reference": "163~170cm",
        "weight_reference": "52~57kg", "bmi_reference": "19.5~21.0", "body_fat_visual_reference": "18~20% 느낌",
        "shoulder": "직각 어깨, 약간 넓음", "ribcage": "보통~넓음 (toned)", "underbust_reference": "70~75cm",
        "bust_volume": "보통, 운동형 상체", "whr_reference": "약 0.73", "leg_ratio_reference": "약 46%",
        "muscle": "높음, 탄탄한 코어와 자연스러운 근육결", "clothing_fit": "크롭·애슬레저·러닝웨어 등에서 운동형 라인이 잘 드러남",
        "sd_difficulty": "높음 · 근육 과장 방지 필요", "bra_example": "",
    },
}


def inferred_profile(body_frame: str) -> str:
    return BODY_FRAME_PROFILE_ALIAS.get(str(body_frame or ""), "균형형")


def profile_reference_rows() -> list[dict[str, Any]]:
    return [{"profile": name, **dict(BODY_PROFILE_META[name])} for name in BODY_PROFILE_MAP]


__all__ = [
    "BODY_PROFILE_MAP", "BODY_FRAME_PROFILE_ALIAS", "BODY_PROFILE_CONTROL_DEFAULTS", "BODY_PROFILE_META",
    "RIBCAGE_MAP", "BUST_VOLUME_MAP", "MUSCLE_TONE_MAP", "LEG_PROPORTION_MAP",
    "inferred_profile", "profile_reference_rows",
]
