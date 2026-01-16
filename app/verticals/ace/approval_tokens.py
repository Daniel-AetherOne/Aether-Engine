from __future__ import annotations

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


class ApprovalTokenService:
    def __init__(self, secret: str, salt: str = "ace-approval-v1"):
        if not secret or len(secret) < 16:
            raise ValueError("APPROVAL_TOKEN_SECRET must be set (min length 16).")
        self._s = URLSafeTimedSerializer(secret_key=secret, salt=salt)

    def make(self, approval_id: str, quote_id: str) -> str:
        return self._s.dumps({"approval_id": approval_id, "quote_id": quote_id})

    def verify(self, token: str, *, max_age_seconds: int) -> dict:
        try:
            return self._s.loads(token, max_age=max_age_seconds)
        except SignatureExpired as e:
            raise ValueError("TOKEN_EXPIRED") from e
        except BadSignature as e:
            raise ValueError("TOKEN_INVALID") from e
