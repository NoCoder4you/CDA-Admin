import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from COGS import NameChange, UserInfo
from COGS.RoleUpdater import AutoRoleUpdater


class NameChangePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "server.json"
        self.initial = {
            "channels": {"verification": 1234},
            "verified_users": [
                {"user_id": "101", "habbo": "OldHabbo", "other_field": "keep"},
                {"user_id": "202", "habbo": "OtherHabbo"},
            ],
        }
        self.write(self.initial)
        name_path = patch.object(NameChange, "SERVER_JSON_PATH", self.path)
        info_path = patch.object(UserInfo, "data_path", return_value=self.path)
        name_path.start()
        info_path.start()
        self.addCleanup(name_path.stop)
        self.addCleanup(info_path.stop)

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_approval_updates_info_and_updater_data_without_reloading_cogs(self):
        info = UserInfo.UserInfoCog.__new__(UserInfo.UserInfoCog)
        updater = AutoRoleUpdater.__new__(AutoRoleUpdater)
        updater.server_data_path = self.path
        updater.server_data = updater.load_server_data()

        self.assertEqual("OldHabbo", info.get_habbo_username("101"))
        NameChange.apply_approved_name_change(101, "OldHabbo", "NewHabbo")
        self.assertEqual("NewHabbo", info.get_habbo_username("101"))

        # The scheduled updater and member-join handler now reload this data.
        updater.server_data = updater.load_server_data()
        self.assertEqual("NewHabbo", updater.server_data["verified_users"][0]["habbo"])
        self.assertEqual("keep", self.read()["verified_users"][0]["other_field"])
        self.assertEqual(self.initial["channels"], self.read()["channels"])
        self.assertEqual(2, len(self.read()["verified_users"]))

    def test_cannot_create_verification_record_for_unverified_member(self):
        with self.assertRaisesRegex(ValueError, "no longer verified"):
            NameChange.apply_approved_name_change(999, "OldHabbo", "NewHabbo")
        self.assertEqual(self.initial, self.read())

    def test_stale_request_does_not_overwrite_newer_approval(self):
        NameChange.apply_approved_name_change(101, "OldHabbo", "FirstChange")
        with self.assertRaisesRegex(ValueError, "fresh name change"):
            NameChange.apply_approved_name_change(101, "OldHabbo", "SecondChange")
        self.assertEqual("FirstChange", self.read()["verified_users"][0]["habbo"])

    def test_failed_write_does_not_return_success(self):
        with patch.object(NameChange, "save_server_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                NameChange.apply_approved_name_change(101, "OldHabbo", "NewHabbo")
        self.assertEqual(self.initial, self.read())


if __name__ == "__main__":
    unittest.main()
