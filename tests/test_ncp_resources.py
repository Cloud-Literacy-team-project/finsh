"""실제 NCP 응답 모양에서 안전한 연결 상태 변환을 확인한다."""

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ncp import blockstorage, publicip


SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def sample(name):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


class ResourceListTests(unittest.TestCase):
    def test_public_ips_use_assignment_and_description(self):
        data = sample("publicip.json")
        items = data["getPublicIpInstanceListResponse"]["publicIpInstanceList"]
        items[0]["publicIpDescription"] = "finsh-test-b-ip1"
        items[1]["serverInstanceNo"] = "2001"
        items[1]["serverName"] = "finsh-test-b-srv1"

        with patch.object(publicip, "call", return_value=data):
            result = publicip.list_all()

        self.assertEqual([r["state"] for r in result], ["DETACHED", "ATTACHED"])
        self.assertEqual(result[0]["name"], "finsh-test-b-ip1")
        self.assertEqual(result[1]["detail"]["attached_server"], "finsh-test-b-srv1")

    def test_public_ip_in_transition_is_not_orphaned(self):
        data = sample("publicip.json")
        item = data["getPublicIpInstanceListResponse"]["publicIpInstanceList"][0]
        item["publicIpInstanceOperation"] = {"code": "ASSOC"}

        with patch.object(publicip, "call", return_value=data):
            result = publicip.list_all()

        self.assertNotEqual(result[0]["state"], "DETACHED")

    def test_storage_detached_and_basic_disk_attached(self):
        data = sample("blockstorage.json")
        with patch.object(blockstorage, "call", return_value=data):
            result = blockstorage.list_all()

        by_name = {r["name"]: r for r in result}
        detached = by_name["finsh-test-b-blk"]
        basic = by_name["finsh-test-b-srv1"]
        self.assertEqual(detached["state"], "DETACHED")
        self.assertEqual(detached["detail"]["size_gb"], 10)
        self.assertEqual(detached["detail"]["storage_type"], "SVRBS")
        self.assertEqual(basic["state"], "ATTACHED")
        self.assertEqual(basic["detail"]["storage_type"], "BASIC")

    def test_storage_with_server_or_operation_is_not_orphaned(self):
        data = sample("blockstorage.json")
        body = data["getBlockStorageInstanceListResponse"]
        item = next(x for x in body["blockStorageInstanceList"] if x["blockStorageName"] == "finsh-test-b-blk")
        item["serverInstanceNo"] = "2001"
        with patch.object(blockstorage, "call", return_value=data):
            result = blockstorage.list_all()
        self.assertNotEqual(next(r for r in result if r["name"] == "finsh-test-b-blk")["state"], "DETACHED")

        data = copy.deepcopy(data)
        item = next(x for x in data["getBlockStorageInstanceListResponse"]["blockStorageInstanceList"] if x["blockStorageName"] == "finsh-test-b-blk")
        item["serverInstanceNo"] = ""
        item["blockStorageInstanceOperation"] = {"code": "DETAC"}
        with patch.object(blockstorage, "call", return_value=data):
            result = blockstorage.list_all()
        self.assertNotEqual(next(r for r in result if r["name"] == "finsh-test-b-blk")["state"], "DETACHED")


if __name__ == "__main__":
    unittest.main()
