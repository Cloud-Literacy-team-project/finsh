import io
import json
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from engine import iac


def state(*resources):
    return {"resources": list(resources)}


def resource(kind, number, mode="managed"):
    return {"mode": mode, "type": kind, "instances": [{"attributes": {"id": number}}]}


class IacTests(unittest.TestCase):
    def test_only_managed_supported_resources_including_modules(self):
        server = resource("ncloud_server", "103")
        server["module"] = "module.lab"
        server["instances"].append({"deposed": "old", "attributes": {"id": "104"}})
        value = state(server, resource("ncloud_public_ip", 903), resource("ncloud_block_storage", "803"),
                      resource("ncloud_login_key", "SECRET"), resource("ncloud_server", "999", "data"))
        self.assertEqual(iac.nos_from_state(value), {"103", "104", "903", "803"})

    def test_invalid_supported_id_blocks_inventory_without_leaking_value(self):
        for value in (None, "SECRET", True):
            with self.assertRaises(iac.IacError) as error:
                iac.nos_from_state(state(resource("ncloud_server", value)))
            self.assertNotIn("SECRET", str(error.exception))

    def test_missing_resources_is_not_empty_inventory(self):
        for value in ({}, {"resources": None}, []):
            with self.assertRaises(iac.IacError):
                iac.nos_from_state(value)
        self.assertEqual(iac.nos_from_state(state()), set())

    def read(self, effects):
        client = Mock()
        client.get_object.side_effect = effects
        with patch.object(iac, "_client", return_value=client), \
             patch.dict(iac.os.environ, {"FINSH_TFSTATE_BUCKET": "test-bucket"}):
            return iac.terraform_nos()

    def test_optional_test_missing_core_is_still_protected(self):
        body = io.BytesIO(json.dumps(state(resource("ncloud_server", "103"))).encode())
        missing = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        self.assertEqual(self.read([{"Body": body}, missing]), {"103"})
        self.assertTrue(body.closed)

    def test_core_missing_must_fail(self):
        with self.assertRaises(iac.IacError):
            self.read([ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")])

    def test_test_denied_is_not_skipped(self):
        with self.assertRaises(iac.IacError):
            self.read([{"Body": io.BytesIO(b'{"resources":[]}')},
                       ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")])

    def test_bad_json_does_not_leak_contents_and_closes_body(self):
        body = io.BytesIO(b'SECRET-PRIVATE-KEY')
        with self.assertRaises(iac.IacError) as error:
            self.read([{"Body": body}])
        self.assertNotIn("SECRET", str(error.exception))
        self.assertIsNone(error.exception.__cause__)
        self.assertTrue(body.closed)

    def test_merge_both_states(self):
        effects = [{"Body": io.BytesIO(json.dumps(state(resource("ncloud_server", no))).encode())}
                   for no in ("103", "105")]
        self.assertEqual(self.read(effects), {"103", "105"})


if __name__ == "__main__":
    unittest.main()
