"""오너클랜 판매사 API 클라이언트.

공식 구조:
- JWT 인증: /auth, service=ownerclan, userType=seller
- GraphQL: /v1/graphql
- production / sandbox 분리

비밀번호는 토큰 발급에만 사용하고 응답/로그에 남기지 않는다.
토큰은 메모리에 캐시하고 인증 오류 시 1회 재발급한다.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

PROD_AUTH = "https://auth.ownerclan.com/auth"
SANDBOX_AUTH = "https://auth-sandbox.ownerclan.com/auth"
PROD_GRAPHQL = "https://api.ownerclan.com/v1/graphql"
SANDBOX_GRAPHQL = "https://api-sandbox.ownerclan.com/v1/graphql"


class OwnerClanAPIError(RuntimeError):
    pass


class OwnerClanClient:
    def __init__(self) -> None:
        s = get_settings()
        self.username = (s.ownerclan_username or "").strip()
        self.password = (s.ownerclan_password or "").strip()
        self.environment = (s.ownerclan_environment or "production").strip().lower()
        if self.environment not in {"production", "sandbox"}:
            self.environment = "production"
        self.auth_url = PROD_AUTH if self.environment == "production" else SANDBOX_AUTH
        self.graphql_url = PROD_GRAPHQL if self.environment == "production" else SANDBOX_GRAPHQL
        self._token = ""
        self._token_expires_at = 0.0

    def is_available(self) -> bool:
        return bool(self.username and self.password)

    @staticmethod
    def _extract_token(data: Any) -> str:
        if isinstance(data, str):
            return data.strip()
        if not isinstance(data, dict):
            return ""
        for key in ("token", "access_token", "accessToken", "jwt", "JWT"):
            value = data.get(key)
            if value:
                return str(value).strip()
        nested = data.get("data")
        if isinstance(nested, dict):
            return OwnerClanClient._extract_token(nested)
        return ""

    def authenticate(self, force: bool = False) -> str:
        if not self.is_available():
            raise OwnerClanAPIError("오너클랜 판매사 ID/PW가 설정되지 않았습니다.")
        if not force and self._token and time.time() < self._token_expires_at - 300:
            return self._token

        payload = {
            "service": "ownerclan",
            "userType": "seller",
            "username": self.username,
            "password": self.password,
        }
        try:
            response = httpx.post(self.auth_url, json=payload, timeout=20)
        except httpx.HTTPError as exc:
            raise OwnerClanAPIError(f"오너클랜 인증 서버 연결 실패: {exc}") from exc
        if response.status_code not in (200, 201):
            raise OwnerClanAPIError(
                f"오너클랜 JWT 발급 실패 HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError:
            data = response.text.strip()
        token = self._extract_token(data)
        if not token:
            raise OwnerClanAPIError("오너클랜 인증 응답에서 JWT 토큰을 찾지 못했습니다.")

        self._token = token
        # 공식 안내는 한 달 유효. 안전하게 29일로 메모리 캐시한다.
        self._token_expires_at = time.time() + 29 * 24 * 60 * 60
        return token

    def graphql(self, query: str, variables: dict[str, Any] | None = None,
                retry_auth: bool = True) -> dict[str, Any]:
        token = self.authenticate()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            response = httpx.post(
                self.graphql_url,
                headers=headers,
                json={"query": query, "variables": variables or {}},
                timeout=40,
            )
        except httpx.HTTPError as exc:
            raise OwnerClanAPIError(f"오너클랜 GraphQL 연결 실패: {exc}") from exc

        if response.status_code in (401, 403) and retry_auth:
            self.authenticate(force=True)
            return self.graphql(query, variables, retry_auth=False)
        if response.status_code != 200:
            raise OwnerClanAPIError(
                f"오너클랜 GraphQL HTTP {response.status_code}: {response.text[:500]}"
            )

        payload = response.json()
        errors = payload.get("errors") or []
        if errors:
            messages = "; ".join(str(e.get("message", e)) for e in errors[:5])
            raise OwnerClanAPIError(f"오너클랜 GraphQL 오류: {messages}")
        return payload.get("data") or {}

    def test_connection(self) -> dict[str, Any]:
        try:
            self.authenticate(force=True)
            data = self.graphql("query { __typename }")
            return {
                "ok": True,
                "environment": self.environment,
                "endpoint": self.graphql_url,
                "typename": data.get("__typename", "Query"),
            }
        except Exception as exc:
            return {"ok": False, "environment": self.environment, "error": str(exc)}

    def get_item(self, key: str) -> dict[str, Any] | None:
        query = """
        query OwnerClanItem($key: ID!) {
          item(key: $key) {
            key
            name
            model
            options {
              price
              quantity
              optionAttributes { name value }
            }
          }
        }
        """
        data = self.graphql(query, {"key": key})
        return data.get("item")

    def list_orders(self, *, first: int = 100, after: str | None = None,
                    date_from: int | None = None, date_to: int | None = None,
                    status: str | None = None) -> dict[str, Any]:
        """판매사 주문을 cursor 방식으로 조회한다. 기간은 API 정책상 90일 이내 권장."""
        query = """
        query OwnerClanOrders($first: Int, $after: String, $dateFrom: Timestamp,
                              $dateTo: Timestamp, $status: OrderStatus) {
          allOrders(first: $first, after: $after, dateFrom: $dateFrom,
                    dateTo: $dateTo, status: $status) {
            pageInfo { hasNextPage endCursor startCursor }
            edges {
              cursor
              node {
                key id status createdAt updatedAt note ordererNote sellerNote
                products {
                  quantity price shippingType itemKey trackingNumber
                  shippingCompanyName shippedDate status
                  itemOptionInfo { price optionAttributes { name value } }
                }
                shippingInfo {
                  shippingFee
                  recipient {
                    name phoneNumber
                    destinationAddress { addr1 addr2 postalCode }
                  }
                }
              }
            }
          }
        }
        """
        variables = {
            "first": max(1, min(int(first), 1000)),
            "after": after,
            "dateFrom": date_from,
            "dateTo": date_to,
            "status": status,
        }
        data = self.graphql(query, variables)
        return data.get("allOrders") or {"pageInfo": {}, "edges": []}

    def get_order(self, key: str) -> dict[str, Any] | None:
        query = """
        query OwnerClanOrder($key: String!) {
          order(key: $key) {
            key id status createdAt updatedAt note ordererNote sellerNote
            products {
              quantity price shippingType itemKey trackingNumber
              shippingCompanyName shippedDate status
              itemOptionInfo { price optionAttributes { name value } }
            }
            shippingInfo {
              shippingFee
              recipient { name phoneNumber destinationAddress { addr1 addr2 postalCode } }
            }
          }
        }
        """
        return self.graphql(query, {"key": key}).get("order")

    def simulate_create_order(self, order_input: dict[str, Any]) -> Any:
        query = """
        query SimulateOwnerClanOrder($input: OrderInput!) {
          simulateCreateOrder(input: $input)
        }
        """
        return self.graphql(query, {"input": order_input}).get("simulateCreateOrder")

    def create_order(self, order_input: dict[str, Any], simulation_result: Any | None = None) -> Any:
        query = """
        mutation CreateOwnerClanOrder($input: OrderInput!, $simulationResult: [OrderSimulationInput]) {
          createOrder(input: $input, simulationResult: $simulationResult) {
            key id status createdAt updatedAt note sellerNote
            products { quantity price itemKey trackingNumber shippingCompanyName shippedDate status }
          }
        }
        """
        variables = {"input": order_input, "simulationResult": simulation_result}
        return self.graphql(query, variables).get("createOrder")

    def cancel_order(self, key: str) -> Any:
        query = """
        mutation CancelOwnerClanOrder($key: ID!) {
          cancelOrder(key: $key) { key id status updatedAt }
        }
        """
        return self.graphql(query, {"key": key}).get("cancelOrder")

    def request_order_cancellation(self, key: str, reason: str) -> Any:
        query = """
        mutation RequestOwnerClanCancellation($key: ID!, $input: RequestOrderCancellationInput!) {
          requestOrderCancellation(key: $key, input: $input) { key id status updatedAt }
        }
        """
        return self.graphql(
            query,
            {"key": key, "input": {"cancelReason": reason}},
        ).get("requestOrderCancellation")


_client: OwnerClanClient | None = None


def get_ownerclan_client() -> OwnerClanClient:
    global _client
    if _client is None:
        _client = OwnerClanClient()
    return _client


def reset_ownerclan_client() -> None:
    global _client
    _client = None
