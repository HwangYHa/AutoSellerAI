"""최근 실수로 만든 로컬 재고 사입 발주서 1건을 긴급 취소한다.

사용:
  python scripts/cancel_latest_purchase_order.py --yes
  python scripts/cancel_latest_purchase_order.py --yes --minutes 30

PurchaseOrder는 AutoSellerAI 내부 재고 사입용 테이블이며 이 스크립트는
외부 공급처에 주문/취소 API를 전송하지 않는다.
"""
from __future__ import annotations

import argparse
import json

from app.services.procurement_safety import cancel_latest_local_purchase_order


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="실제 취소 실행")
    parser.add_argument("--minutes", type=int, default=180, help="최근 N분 내 발주만 대상")
    args = parser.parse_args()

    if not args.yes:
        print("취소를 실행하려면 --yes를 붙이세요.")
        return 2

    result = cancel_latest_local_purchase_order(max_age_minutes=args.minutes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
