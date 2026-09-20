"""Small, defensive client for the external account service."""

from __future__ import annotations

from typing import Any

import requests

from rag.common.configuration import AuthServiceConfig


class AuthServiceError(RuntimeError):
    """A user-safe account-service failure."""

    def __init__(self, public_message: str, status_code: int = 502):
        super().__init__(public_message)
        self.public_message = public_message
        self.status_code = status_code


class AuthServiceClient:
    def __init__(self, config: AuthServiceConfig):
        self.config = config

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.request(
                method,
                self.config.endpoint(path),
                json=payload,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise AuthServiceError("账号服务暂时不可用，请稍后重试。", 503) from exc

        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.ok:
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, list):
                detail = "；".join(str(item.get("msg", item)) for item in detail)
            if response.status_code in (401, 403):
                raise AuthServiceError("登录凭证无效或已过期，请重新登录。", 401)
            raise AuthServiceError(
                str(detail or f"账号服务请求失败（HTTP {response.status_code}）"),
                502,
            )
        if not isinstance(body, dict):
            raise AuthServiceError("账号服务返回了无效数据。")
        return body

    def captcha(self, phone: str) -> dict[str, Any]:
        return self._request("POST", self.config.captcha_path, payload={"phone": phone})

    def send_sms(self, phone: str, captcha_id: str, answer: str) -> None:
        result = self._request(
            "POST",
            self.config.sms_send_path,
            payload={
                "phone": phone,
                "captcha_id": captcha_id,
                "captcha_answer": answer,
            },
        )
        if result.get("success") is not True:
            raise AuthServiceError("短信验证码发送失败，请稍后重试。")

    def sms_login(self, phone: str, code: str, privacy_agreed: bool) -> str:
        result = self._request(
            "POST",
            self.config.sms_login_path,
            payload={
                "phone": phone,
                "code": code,
                "source": "web",
                "privacy_agreed": privacy_agreed,
            },
        )
        return self._token(result)

    def password_login(self, phone: str, password: str) -> str:
        result = self._request(
            "POST",
            self.config.password_login_path,
            payload={"phone": phone, "password": password, "source": "web"},
        )
        return self._token(result)

    def profile(self, token: str) -> dict[str, Any]:
        return self._request("GET", self.config.profile_path, token=token)

    def set_password(self, token: str, old_password: str, new_password: str) -> None:
        self._request(
            "POST",
            self.config.set_password_path,
            payload={"old_password": old_password, "password": new_password},
            token=token,
        )

    def logout(self, token: str) -> None:
        self._request("POST", self.config.logout_path, token=token)

    @staticmethod
    def _token(result: dict[str, Any]) -> str:
        token = str(result.get("access_token") or "").strip()
        if not token:
            raise AuthServiceError("账号服务未返回登录凭证。")
        return token
