"""네이버 클라우드 API 공통 요청 함수.

예)
    call("/vserver/v2/getServerInstanceList")                       # 서버 API (GET)
    call("/cw_fea/real/cw/api/schema/system/list", base=INSIGHT)    # 다른 주소
    call("/cw_fea/real/cw/api/data/query", method="POST", base=INSIGHT, body={...})
    call(..., account="SCANNER")   # FINSH_SCANNER_ACCESS_KEY / SECRET_KEY 사용
"""
import base64
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()  # finsh 폴더의 .env를 자동으로 읽음

SERVER = "https://ncloud.apigw.ntruss.com"
INSIGHT = "https://cw.apigw.ntruss.com"
BILLING = "https://billingapi.apigw.ntruss.com"
ADVISOR = "https://cloud-advisor.apigw.ntruss.com"

# 이 주소들은 responseFormatType=json 을 붙여야 JSON으로 답한다
NEEDS_FORMAT = (SERVER, BILLING)


def _keys(account=None):
    """account=None 이면 내 키(NCLOUD_*), 아니면 FINSH_{account}_ACCESS_KEY 등."""
    if account is None:
        ak, sk = "NCLOUD_ACCESS_KEY", "NCLOUD_SECRET_KEY"
    else:
        ak, sk = f"FINSH_{account.upper()}_ACCESS_KEY", f"FINSH_{account.upper()}_SECRET_KEY"
    access_key, secret_key = os.environ.get(ak), os.environ.get(sk)
    if not access_key or not secret_key:
        raise RuntimeError(f".env에 {ak}, {sk} 값이 없습니다")
    return access_key, secret_key


def _sign(method, uri, timestamp, access_key, secret_key):
    message = f"{method} {uri}\n{timestamp}\n{access_key}"
    digest = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def call(path, params=None, method="GET", base=SERVER, body=None, account=None):
    access_key, secret_key = _keys(account)

    params = dict(params or {})
    if base in NEEDS_FORMAT:
        params.setdefault("responseFormatType", "json")
    uri = f"{path}?{urlencode(params)}" if params else path

    timestamp = str(int(time.time() * 1000))
    headers = {
        "x-ncp-apigw-timestamp": timestamp,
        "x-ncp-iam-access-key": access_key,
        "x-ncp-apigw-signature-v2": _sign(method, uri, timestamp, access_key, secret_key),
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    response = requests.request(method, base + uri, headers=headers, json=body, timeout=15)
    if response.status_code >= 400:
        raise RuntimeError(f"NCP API 오류 {response.status_code}: {response.text[:300]}")
    return response.json()