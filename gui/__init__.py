"""오토셀러AI 사용자 화면 패키지."""
from gui import korean_runtime
from gui.korean_safe import install_safe_translate

install_safe_translate()

from gui.korean_runtime_extra import apply_extra_korean_patch
from gui.pageconfig_ko import patch_page_config

korean_runtime.apply_korean_patch()
apply_extra_korean_patch()
patch_page_config()
