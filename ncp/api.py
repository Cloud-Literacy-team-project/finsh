import base64
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests

BASE_URL = "https://ncloud.apigw.ntruss.com"


def call(path, params=None):
    access_key = os.environ["NCLOUD_ACCESS_KEY"]
    secret_key = os.environ["NCLOUD_SECRET_KEY"]

    query = urlencode({"responseFormatType": "json", **(params or {})})
    uri = f"{path}?{query}"
    timestamp = str(int(time.time() * 1000))

    message = f"GET {uri}\n{timestamp}\n{access_key}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(digest).decode("utf-8")

    headers = {
        "x-ncp-apigw-timestamp": timestamp,
        "x-ncp-iam-access-key": access_key,
        "x-ncp-apigw-signature-v2": signature,
    }

    response = requests.get(BASE_URL + uri, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()