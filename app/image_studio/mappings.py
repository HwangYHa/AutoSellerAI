"""Korean UI labels -> model-agnostic Stable Diffusion prompt fragments.

The mappings intentionally use descriptive photographic language instead of
checkpoint-specific trigger words.  This keeps the same UI usable across SD 1.5,
SDXL and compatible photoreal checkpoints.  Character age choices are adult-only.

Body controls describe *visual proportions and silhouette*, not exact centimetre
measurements. Text-to-image models cannot reliably guarantee exact body sizes, and
qualitative visual language produces more stable commercial/lifestyle results.
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
    "50대": "in their fifties, mature adult appearance",
}

HAIR_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 단발": "natural short bob haircut",
    "턱선 단발": "chin-length bob haircut",
    "C컬 단발": "chin-length bob with soft inward C-curl ends",
    "S컬 단발": "short bob with soft S-shaped waves",
    "보브컷": "clean contemporary bob haircut",
    "픽시컷": "neat modern pixie haircut",
    "숏컷": "clean short haircut",
    "중단발": "natural shoulder-length lob haircut",
    "중단발 웨이브": "shoulder-length hair with soft natural waves",
    "긴 생머리": "long straight hair",
    "긴 웨이브": "long soft wavy hair",
    "굵은 웨이브": "long hair with large loose waves",
    "잔잔한 웨이브": "long hair with subtle fine waves",
    "레이어드컷": "soft layered haircut",
    "허쉬컷": "modern soft hush cut with airy layers",
    "긴 레이어드": "long layered hair with natural movement",
    "포니테일": "neat natural ponytail",
    "하이 포니테일": "clean high ponytail with natural volume",
    "로우 포니테일": "soft low ponytail",
    "로우번": "clean low bun hairstyle",
    "하이번": "neat high bun hairstyle",
    "반묶음": "natural half-up half-down hairstyle",
    "가르마 헤어": "neat side-parted hair",
    "쉼표 머리": "soft comma hairstyle",
    "댄디컷": "clean Korean dandy haircut",
    "리젠트컷": "neat short regent hairstyle",
    "투블럭": "clean two-block Korean haircut",
    "가일컷": "modern Korean guile haircut with natural parting",
}

HAIR_COLOR_MAP: Mapping[str, str] = {
    "검정": "natural black hair",
    "소프트 블랙": "soft natural black hair with subtle highlights",
    "다크브라운": "dark brown hair",
    "초코브라운": "rich chocolate brown hair",
    "브라운": "natural brown hair",
    "애쉬브라운": "soft ash brown hair",
    "밝은 브라운": "light warm brown hair",
    "밀크브라운": "soft milk-brown hair",
    "카키브라운": "subtle khaki brown hair",
    "레드브라운": "natural reddish brown hair",
    "애쉬그레이": "subtle ash gray hair",
    "내추럴 그레이": "natural mature gray hair",
}

FACE_SHAPE_MAP: Mapping[str, str] = {
    "계란형": "balanced oval face",
    "갸름한형": "slender softly tapered face",
    "둥근형": "soft round face",
    "각진형": "subtly defined angular face",
    "하트형": "soft heart-shaped face",
    "긴 얼굴형": "naturally elongated balanced face",
    "짧은 얼굴형": "compact balanced face proportions",
    "V라인형": "softly tapered V-shaped jawline without exaggeration",
    "광대가 은은한형": "subtle natural cheekbone definition",
    "턱선이 또렷한형": "clean naturally defined jawline",
}

EYE_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 눈매": "natural balanced eyes",
    "또렷한 눈매": "clear defined eyes",
    "부드러운 눈매": "soft gentle eyes",
    "고양이상": "slightly upturned cat-like eyes",
    "강아지상": "warm softly rounded eyes",
    "아몬드형": "natural almond-shaped eyes",
    "둥근 눈매": "soft naturally rounded eyes",
    "길고 시원한 눈매": "slightly elongated open eye shape",
    "살짝 올라간 눈꼬리": "subtly upturned outer eye corners",
    "살짝 내려간 눈꼬리": "subtly downturned gentle outer eye corners",
    "쌍꺼풀 또렷": "natural defined double eyelids",
    "속쌍 느낌": "subtle inner double eyelid appearance",
    "무쌍 느낌": "natural monolid eye shape",
    "차분한 눈빛": "calm composed gaze with relaxed eyes",
}

NOSE_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 코": "natural proportional nose",
    "오똑한 코": "clean defined nose bridge",
    "부드러운 코선": "soft natural nose profile",
    "슬림한 콧대": "slender natural nose bridge",
    "직선형 콧대": "straight natural nose bridge",
    "살짝 둥근 코끝": "soft subtly rounded nose tip",
    "작고 단정한 코": "small neat proportional nose",
    "남성적인 코선": "defined masculine but proportional nose profile",
}

LIP_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 입술": "natural proportional lips",
    "도톰한 입술": "soft naturally full lips",
    "얇고 정돈된 입술": "neat subtly thin lips",
    "윗입술 얇고 아랫입술 도톰": "subtle thinner upper lip and naturally fuller lower lip",
    "입꼬리 살짝 올라감": "subtly upturned mouth corners",
    "선명한 립라인": "clean natural lip contour",
    "부드러운 립라인": "soft blended natural lip contour",
    "작고 단정한 입술": "small neat proportional lips",
}

SKIN_TONE_MAP: Mapping[str, str] = {
    "매우 밝은 뉴트럴": "very light neutral Korean skin tone with realistic undertones",
    "밝은 뉴트럴": "light neutral Korean skin tone",
    "밝은 웜": "light warm Korean skin tone",
    "내추럴": "natural Korean skin tone",
    "뉴트럴": "balanced neutral Korean skin tone",
    "웜": "warm healthy Korean skin tone",
    "살짝 태닝": "lightly sun-kissed Korean skin tone",
    "건강한 태닝": "healthy moderate sun-kissed Korean skin tone",
}

EXPRESSION_MAP: Mapping[str, str] = {
    "무표정/차분": "calm relaxed expression",
    "은은한 미소": "subtle natural smile",
    "밝은 미소": "bright friendly smile",
    "활짝 웃음": "open cheerful natural smile",
    "자신감 있는 표정": "confident composed expression",
    "장난스러운 표정": "playful friendly expression",
    "살짝 수줍은 미소": "subtle shy warm smile",
    "도도한 표정": "restrained elegant confident expression",
    "시크한 표정": "cool composed expression",
    "편안한 표정": "comfortable relaxed facial expression",
    "진지한 표정": "serious focused expression without tension",
    "호기심 있는 표정": "subtle curious attentive expression",
    "따뜻한 표정": "warm empathetic expression",
    "카메라 의식 없는 표정": "natural candid expression as if unaware of camera",
}

BODY_FRAME_MAP: Mapping[str, str] = {
    "매우 슬림": "very slim delicate adult physique with natural healthy proportions",
    "아담한 체형": "petite naturally proportioned adult body",
    "슬림": "slim naturally proportioned adult body",
    "슬림 균형형": "slim balanced adult physique with natural proportions",
    "슬림 글래머": "slim adult physique with a naturally curvier feminine silhouette and realistic proportions",
    "균형형": "balanced natural adult body proportions",
    "자연스러운 볼륨형": "naturally curvy balanced adult silhouette",
    "볼륨형": "fuller naturally curvy adult silhouette with realistic balanced proportions",
    "애슬레틱": "fit athletic adult physique with natural proportions",
    "탄탄한 체형": "toned healthy adult physique",
    "러너형": "lean athletic adult physique with light muscle definition",
    "근육형": "athletic muscular adult physique with realistic moderate definition",
}

HEIGHT_MAP: Mapping[str, str] = {
    "매우 아담한 인상": "very petite adult height impression",
    "아담한 인상": "petite height impression",
    "평균적인 인상": "average height impression",
    "큰 키 인상": "tall elegant height impression",
    "매우 큰 키 인상": "very tall fashion-model-like height impression with natural proportions",
}

SHOULDER_MAP: Mapping[str, str] = {
    "좁고 부드러운 어깨": "soft narrow shoulder line",
    "살짝 좁은 어깨": "slightly narrow natural shoulder proportions",
    "균형 잡힌 어깨": "balanced shoulder proportions",
    "살짝 넓은 어깨": "slightly broad natural shoulder line",
    "곧고 탄탄한 어깨": "straight toned shoulder line",
    "넓고 탄탄한 어깨": "broad athletic shoulders with realistic proportions",
}

WAIST_HIP_MAP: Mapping[str, str] = {
    "일자형": "straight natural waist and hip silhouette",
    "슬림 일자형": "slender straight waist and hip silhouette",
    "균형형": "balanced natural waist and hip proportions",
    "허리선 강조형": "gently defined waistline with natural proportions",
    "곡선형": "gently curved natural waist and hip silhouette",
    "모래시계형": "natural hourglass-inspired waist and hip silhouette without exaggeration",
    "애슬레틱 힙라인": "toned athletic waist and hip silhouette",
}

CHEST_PROPORTION_MAP: Mapping[str, str] = {
    "매우 슬림한 상체": "very slender upper-body proportions with natural anatomy",
    "슬림한 상체": "slender upper-body proportions",
    "자연스러운 비율": "natural proportional torso",
    "균형 잡힌 상체": "balanced natural upper-body proportions",
    "자연스러운 볼륨감": "naturally fuller but realistic upper-body proportions",
    "탄탄한 상체": "fit toned upper-body proportions with realistic anatomy",
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
    "화이트 셔츠 코디": "wearing a crisp white shirt with clean modern styling",
    "블라우스 코디": "wearing a refined contemporary blouse with tasteful bottoms",
    "셔츠+슬랙스": "wearing a clean shirt with tailored slacks",
    "티셔츠+데님": "wearing a clean fitted T-shirt with modern denim",
    "니트+데님": "wearing a soft knit top with modern denim",
    "가디건 코디": "wearing a tasteful cardigan layered over a simple top",
    "후드 캐주얼": "wearing a clean contemporary hoodie casual outfit",
    "맨투맨 캐주얼": "wearing a minimal sweatshirt with relaxed casual bottoms",
    "데님 셋업": "wearing a tasteful modern denim coordinated outfit",
    "트렌치코트": "wearing a classic contemporary trench coat outfit",
    "롱코트": "wearing a refined long coat with minimal styling",
    "블레이저룩": "wearing a tailored blazer with contemporary styling",
    "비즈니스 캐주얼": "wearing polished modern business-casual clothing",
    "럭셔리 미니멀": "wearing understated luxury minimalist fashion",
    "리조트룩": "wearing elegant relaxed resort clothing",
    "바캉스룩": "wearing tasteful light vacation clothing",
    "골프 캐주얼": "wearing clean modern golf-inspired casual clothing",
    "테니스 캐주얼": "wearing tasteful tennis-inspired athleisure",
    "러닝웨어": "wearing functional clean modern running apparel",
    "요가/필라테스룩": "wearing tasteful fitted studio activewear",
    "하객룩": "wearing polished elegant wedding-guest fashion",
    "데이트룩": "wearing refined approachable date-night casual fashion",
    "미팅룩": "wearing professional modern meeting attire",
    "공항패션": "wearing comfortable polished airport fashion",
    "홈웨어": "wearing tasteful comfortable modern loungewear",
}

OUTFIT_COLOR_MAP: Mapping[str, str] = {
    "자동/자연스럽게": "harmonious neutral clothing colors",
    "블랙": "predominantly black outfit",
    "화이트": "predominantly white outfit",
    "아이보리/베이지": "ivory and beige color palette",
    "크림": "soft cream clothing palette",
    "브라운": "warm brown color palette",
    "카멜": "warm camel color palette",
    "그레이": "clean gray color palette",
    "차콜": "deep charcoal color palette",
    "네이비": "refined navy color palette",
    "블루": "clean balanced blue color palette",
    "스카이블루": "soft sky-blue color palette",
    "올리브/카키": "muted olive and khaki color palette",
    "버건디": "refined burgundy color palette",
    "레드 포인트": "neutral outfit with a tasteful red accent",
    "파스텔": "soft tasteful pastel color palette",
    "모노톤": "clean monochrome clothing palette",
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
    "감성적": "soft emotional lifestyle atmosphere",
    "미니멀": "clean restrained minimalist atmosphere",
    "내추럴 라이프스타일": "authentic relaxed lifestyle atmosphere",
    "패셔너블": "fashion-forward polished atmosphere",
    "프로페셔널": "professional trustworthy polished atmosphere",
    "활기찬": "bright energetic lively atmosphere",
    "차분한": "quiet calm composed atmosphere",
    "시네마틱": "cinematic realistic dramatic atmosphere without fantasy styling",
}

PERSONALITY_MAP: Mapping[str, str] = {
    "밝고 친근함": "friendly open body language and warm presence",
    "차분하고 지적": "calm intelligent composed presence",
    "자신감 있음": "confident poised body language",
    "사랑스럽고 부드러움": "gentle approachable body language",
    "활발하고 에너지 있음": "energetic upbeat natural body language",
    "시크하고 절제됨": "restrained chic confident presence",
    "유쾌하고 장난기 있음": "playful humorous approachable presence",
    "성숙하고 안정적": "mature stable trustworthy presence",
    "독립적이고 당당함": "independent self-assured poised presence",
    "다정하고 편안함": "kind relaxed comforting presence",
    "호기심 많고 생동감 있음": "curious lively attentive presence",
    "프로페셔널하고 냉정함": "professional focused controlled presence",
    "감성적이고 부드러움": "soft sensitive thoughtful presence",
    "스포티하고 건강함": "healthy active energetic presence",
}

POSE_MAP: Mapping[str, str] = {
    "자연스럽게 서기": "natural relaxed standing pose",
    "카메라 바라보기": "looking naturally toward the camera",
    "살짝 측면": "subtle three-quarter body angle",
    "걷는 순간": "natural candid walking moment",
    "의자에 앉기": "natural seated pose with relaxed posture",
    "상품을 들고 있기": "naturally holding the featured product with anatomically correct hands",
    "한 손 주머니": "relaxed standing pose with one hand naturally in a pocket",
    "양손 주머니": "relaxed pose with both hands naturally in pockets",
    "팔짱 가볍게": "light relaxed folded-arm pose without stiffness",
    "벽에 살짝 기대기": "natural relaxed pose lightly leaning against a wall",
    "테이블에 앉기": "natural seated pose at a table with relaxed posture",
    "소파에 앉기": "relaxed natural seated pose on a sofa",
    "창밖 바라보기": "candid pose looking naturally out a window",
    "옆을 바라보기": "natural gaze slightly away from camera",
    "뒤돌아보기": "natural over-the-shoulder glance with realistic posture",
    "머리카락 정리하기": "natural candid gesture gently adjusting hair with correct hands",
    "커피컵 들기": "naturally holding a coffee cup with anatomically correct fingers",
    "스마트폰 보기": "naturally holding and looking at a smartphone with correct hands",
    "가방 들기": "naturally carrying a fashion bag with realistic hand grip",
    "재킷 정리하기": "naturally adjusting jacket or lapel with realistic hands",
    "계단 걷기": "natural candid moment walking on stairs",
    "횡단보도 걷기": "natural urban candid walking across a crosswalk",
}

SHOT_MAP: Mapping[str, str] = {
    "얼굴 클로즈업": "close-up portrait, face and shoulders clearly framed",
    "바스트샷": "bust portrait framed from chest upward",
    "상반신": "upper-body portrait, torso clearly visible",
    "허리 위": "waist-up portrait with natural body framing",
    "허벅지 위": "three-quarter portrait framed above the knees",
    "무릎 위": "knee-up fashion portrait with complete upper legs visible",
    "전신": "full-body fashion photograph, entire body and feet visible",
    "환경 포함 전신": "full-body environmental portrait with complete body and surrounding scene visible",
}

BACKGROUND_MAP: Mapping[str, str] = {
    "화이트 스튜디오": "clean white photography studio background",
    "그레이 스튜디오": "clean neutral gray photography studio background",
    "베이지 스튜디오": "warm minimal beige photography studio background",
    "감성 카페": "tasteful contemporary cafe interior",
    "브런치 카페": "bright modern brunch cafe interior",
    "미니멀 갤러리": "minimal modern art gallery interior",
    "모던 오피스": "modern refined office interior",
    "회의실": "clean premium modern conference room interior",
    "코워킹 스페이스": "stylish contemporary coworking space",
    "도심 스트릿": "clean contemporary Korean urban street",
    "서울 골목": "tasteful contemporary Seoul side-street setting",
    "빌딩 숲": "modern Korean business-district cityscape",
    "편안한 집": "tasteful cozy modern apartment interior",
    "미니멀 거실": "clean minimalist modern living room",
    "주방": "bright tasteful contemporary kitchen interior",
    "호텔 라운지": "understated upscale hotel lounge",
    "호텔 룸": "clean upscale modern hotel room interior",
    "백화점/쇼핑몰": "premium contemporary department-store interior",
    "서점": "warm modern bookstore interior",
    "도서관": "quiet refined contemporary library interior",
    "한강/공원": "clean urban riverside park setting",
    "도심 공원": "green contemporary urban park setting",
    "해변": "bright natural beach setting",
    "바닷가 산책로": "clean coastal promenade with natural sea background",
    "루프탑": "modern rooftop terrace with realistic city background",
    "지하철역": "clean contemporary Korean subway-station environment",
    "공항": "bright modern international airport interior",
    "주차장": "clean modern indoor parking structure with balanced lighting",
    "자동차 옆": "modern street or parking setting beside a clean contemporary car",
    "캠퍼스": "modern Korean university campus setting",
}

LIGHTING_MAP: Mapping[str, str] = {
    "부드러운 자연광": "soft diffused natural daylight, realistic skin illumination",
    "창가 자연광": "soft window daylight with realistic directional shadows",
    "밝은 스튜디오": "clean softbox studio lighting with balanced exposure",
    "뷰티 소프트박스": "large softbox beauty lighting with natural skin detail and soft shadows",
    "골든아워": "warm golden-hour natural light with controlled highlights",
    "블루아워": "soft blue-hour ambient light with realistic skin exposure",
    "흐린날 소프트광": "soft overcast daylight with even skin tones",
    "맑은날 자연광": "clean bright daylight with controlled realistic highlights",
    "실내 웜톤": "warm indoor practical lighting with realistic mixed-light balance",
    "카페 조명": "warm cafe practical lighting balanced with soft ambient daylight",
    "오피스 조명": "clean neutral office lighting with natural skin rendering",
    "역광 림라이트": "controlled natural backlight with subtle realistic rim light",
    "측면광": "soft directional side lighting with natural facial contour",
    "시네마틱": "controlled cinematic key light with realistic fill light",
}

DOF_MAP: Mapping[str, str] = {
    "배경까지 선명": "deep depth of field, subject and background both clearly resolved",
    "자연스러운 심도": "natural moderate depth of field, subject clearly focused",
    "인물 중심": "gentle subject separation with a recognizable background",
    "강한 인물 분리": "strong subject separation with soft but recognizable background detail",
    "스마트폰식 전체 초점": "smartphone-like broad focus with most scene details clearly resolved",
}

CAMERA_MAP: Mapping[str, str] = {
    "자연스러운 스마트폰 사진": "high-end smartphone lifestyle photography, natural perspective",
    "스마트폰 광각": "high-end smartphone wide-angle lifestyle photography with controlled perspective distortion",
    "24mm 환경 인물": "24mm environmental portrait photography with carefully controlled wide perspective",
    "28mm 스트릿": "28mm candid street portrait photography with natural environmental context",
    "35mm 환경 인물": "35mm environmental portrait photography, natural perspective",
    "40mm 라이프스타일": "40mm lifestyle portrait photography with balanced environment and subject",
    "50mm 자연 인물": "50mm portrait photography, realistic perspective",
    "70mm 패션": "70mm fashion portrait photography with mild flattering compression",
    "85mm 패션 인물": "85mm fashion portrait photography, flattering realistic perspective",
    "105mm 뷰티": "105mm beauty portrait photography with natural flattering compression",
    "룩북 카메라": "professional commercial lookbook photography with neutral perspective",
    "SNS 스냅": "premium social-media lifestyle snapshot with believable handheld framing",
}

PRESETS = {
    "실사 인플루언서": {
        "shot": "상반신", "background": "감성 카페", "lighting": "창가 자연광",
        "camera": "50mm 자연 인물", "dof": "자연스러운 심도", "steps": 30,
        "cfg_scale": 6.0, "width": 768, "height": 1152, "hires": True,
    },
    "쇼핑몰 모델컷": {
        "shot": "전신", "background": "화이트 스튜디오", "lighting": "밝은 스튜디오",
        "camera": "50mm 자연 인물", "dof": "배경까지 선명", "steps": 32,
        "cfg_scale": 6.0, "width": 768, "height": 1152, "hires": True,
    },
    "Threads/SNS 세로컷": {
        "shot": "허벅지 위", "background": "도심 스트릿", "lighting": "부드러운 자연광",
        "camera": "35mm 환경 인물", "dof": "자연스러운 심도", "steps": 28,
        "cfg_scale": 5.5, "width": 768, "height": 1152, "hires": True,
    },
    "감성 프로필": {
        "shot": "얼굴 클로즈업", "background": "미니멀 갤러리", "lighting": "창가 자연광",
        "camera": "85mm 패션 인물", "dof": "인물 중심", "steps": 30,
        "cfg_scale": 5.5, "width": 832, "height": 1216, "hires": True,
    },
    "오피스 프로필": {
        "shot": "상반신", "background": "모던 오피스", "lighting": "밝은 스튜디오",
        "camera": "50mm 자연 인물", "dof": "배경까지 선명", "steps": 30,
        "cfg_scale": 6.0, "width": 768, "height": 1152, "hires": True,
    },
    "프리미엄 룩북": {
        "shot": "전신", "background": "베이지 스튜디오", "lighting": "뷰티 소프트박스",
        "camera": "70mm 패션", "dof": "자연스러운 심도", "steps": 34,
        "cfg_scale": 5.5, "width": 832, "height": 1216, "hires": True,
    },
    "도심 스트릿 스냅": {
        "shot": "환경 포함 전신", "background": "도심 스트릿", "lighting": "부드러운 자연광",
        "camera": "35mm 환경 인물", "dof": "자연스러운 심도", "steps": 28,
        "cfg_scale": 5.5, "width": 768, "height": 1152, "hires": True,
    },
    "카페 라이프스타일": {
        "shot": "허리 위", "background": "브런치 카페", "lighting": "카페 조명",
        "camera": "40mm 라이프스타일", "dof": "인물 중심", "steps": 28,
        "cfg_scale": 5.5, "width": 768, "height": 1152, "hires": True,
    },
    "스마트폰 일상 스냅": {
        "shot": "허벅지 위", "background": "도심 스트릿", "lighting": "부드러운 자연광",
        "camera": "자연스러운 스마트폰 사진", "dof": "스마트폰식 전체 초점", "steps": 26,
        "cfg_scale": 5.0, "width": 768, "height": 1152, "hires": True,
    },
    "비즈니스 프로필": {
        "shot": "바스트샷", "background": "그레이 스튜디오", "lighting": "뷰티 소프트박스",
        "camera": "85mm 패션 인물", "dof": "인물 중심", "steps": 30,
        "cfg_scale": 5.5, "width": 896, "height": 1152, "hires": True,
    },
    "해변 라이프스타일": {
        "shot": "환경 포함 전신", "background": "해변", "lighting": "골든아워",
        "camera": "35mm 환경 인물", "dof": "자연스러운 심도", "steps": 30,
        "cfg_scale": 5.5, "width": 768, "height": 1152, "hires": True,
    },
    "공항 패션": {
        "shot": "전신", "background": "공항", "lighting": "부드러운 자연광",
        "camera": "50mm 자연 인물", "dof": "배경까지 선명", "steps": 30,
        "cfg_scale": 5.5, "width": 768, "height": 1152, "hires": True,
    },
}


PROMPT_MAPS: Mapping[str, Mapping[str, str]] = {
    "gender": GENDER_MAP,
    "age": AGE_MAP,
    "hair_style": HAIR_STYLE_MAP,
    "hair_color": HAIR_COLOR_MAP,
    "face_shape": FACE_SHAPE_MAP,
    "eye_style": EYE_STYLE_MAP,
    "nose_style": NOSE_STYLE_MAP,
    "lip_style": LIP_STYLE_MAP,
    "skin_tone": SKIN_TONE_MAP,
    "expression": EXPRESSION_MAP,
    "body_frame": BODY_FRAME_MAP,
    "height_impression": HEIGHT_MAP,
    "shoulder": SHOULDER_MAP,
    "waist_hip": WAIST_HIP_MAP,
    "chest_proportion": CHEST_PROPORTION_MAP,
    "outfit": OUTFIT_MAP,
    "outfit_color": OUTFIT_COLOR_MAP,
    "mood": MOOD_MAP,
    "personality": PERSONALITY_MAP,
    "pose": POSE_MAP,
    "shot": SHOT_MAP,
    "background": BACKGROUND_MAP,
    "lighting": LIGHTING_MAP,
    "depth_of_field": DOF_MAP,
    "camera": CAMERA_MAP,
}


def option_keys(mapping: Mapping[str, str]) -> list[str]:
    return list(mapping.keys())


def mapping_stats() -> dict[str, int]:
    """Return deterministic option counts for API/UI diagnostics and tests."""
    result = {name: len(mapping) for name, mapping in PROMPT_MAPS.items()}
    result["total"] = sum(result.values())
    result["presets"] = len(PRESETS)
    return result


__all__ = [name for name in globals() if name.endswith("_MAP")] + [
    "PRESETS", "PROMPT_MAPS", "option_keys", "mapping_stats"
]
