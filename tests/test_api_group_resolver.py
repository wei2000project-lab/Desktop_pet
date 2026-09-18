import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock, patch

from app.settings import (
    APIGroup, APIGroupKey, APIGroupSettings, APIGroupService,
    APIGroupResolutionError, resolve_api_request,
)
from app.settings.api_groups import serialize_api_groups


def stored(key_id, priority=1, enabled=True):
    return APIGroupKey(key_id, key_id, f"fake-{key_id}", priority, enabled)


def environment_key(key_id="env", priority=1, enabled=True):
    return APIGroupKey(key_id, key_id, priority=priority, enabled=enabled,
                       source="environment", environment_variable="OPENAI_API_KEY")


def settings_with(keys=(), auth_mode="api_key"):
    group = APIGroup("selected", "群組", "https://example.test/v1/", "test-model",
                     temperature=1.2, verify_ssl=False, auth_mode=auth_mode, keys=keys)
    return APIGroupSettings((group,), group.id)


class NeverReadEnvironment(dict):
    def get(self, *_args):
        raise AssertionError("Environment must not be read")


class APIGroupResolverTests(unittest.TestCase):
    def assert_error(self, settings, code, **kwargs):
        with self.assertRaises(APIGroupResolutionError) as raised:
            resolve_api_request(settings, **kwargs)
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn("fake-", str(raised.exception))

    def test_group_fields_are_preserved_and_first_key_selected(self):
        snapshot = resolve_api_request(settings_with((stored("first"),)))
        self.assertEqual((snapshot.group_id, snapshot.group_name, snapshot.base_url,
                          snapshot.model, snapshot.temperature, snapshot.verify_ssl, snapshot.auth_mode),
                         ("selected", "群組", "https://example.test/v1", "test-model", 1.2, False, "api_key"))
        self.assertEqual(snapshot.selected_key.id, "first")
        self.assertEqual(snapshot.api_key, "fake-first")
        self.assertNotIn("fake-first", repr(snapshot))

    def test_priority_sort_and_equal_priority_stable_order(self):
        settings = settings_with((stored("later", 10), stored("first", 1), stored("second", 1), stored("middle", 2)))
        snapshot = resolve_api_request(settings)
        self.assertEqual([key.id for key in snapshot.candidates], ["first", "second", "middle", "later"])
        self.assertEqual([key.id for key in settings.groups[0].keys], ["later", "first", "second", "middle"])

    def test_disabled_keys_excluded_without_changing_priority(self):
        settings = settings_with((stored("paused", 1, False), stored("active", 4)))
        snapshot = resolve_api_request(settings)
        self.assertEqual(snapshot.selected_key.id, "active")
        self.assertEqual(settings.groups[0].keys[0].priority, 1)
        self.assertFalse(settings.groups[0].keys[0].enabled)

    def test_missing_empty_and_no_active_group_are_distinct(self):
        self.assert_error(None, "not_configured")
        self.assert_error(APIGroupSettings(), "not_configured")
        self.assert_error(replace(settings_with((stored("one"),)), active_group_id=None), "no_active_group")

    def test_no_keys_all_disabled_and_missing_environment_are_distinct(self):
        self.assert_error(settings_with(), "no_keys")
        self.assert_error(settings_with((stored("paused", enabled=False),)), "all_keys_disabled")
        self.assert_error(settings_with((environment_key(),)), "environment_unavailable", environment={})

    def test_blank_or_non_string_environment_values_are_unusable(self):
        for value in ("", "  ", None, 123):
            with self.subTest(value=value):
                self.assert_error(settings_with((environment_key(),)), "environment_unavailable",
                                  environment={"OPENAI_API_KEY": value})

    def test_missing_environment_skips_to_stored_candidate(self):
        snapshot = resolve_api_request(settings_with((environment_key(), stored("backup", 2))), environment={})
        self.assertEqual(snapshot.api_key, "fake-backup")
        self.assertEqual(len(snapshot.candidates), 1)

    def test_explicit_environment_value_is_resolved_only_into_snapshot(self):
        settings = settings_with((environment_key(), stored("backup", 2)))
        before = serialize_api_groups(settings)
        snapshot = resolve_api_request(settings, environment={"OPENAI_API_KEY": " fake-env-secret "})
        self.assertEqual(snapshot.api_key, "fake-env-secret")
        self.assertNotIn("fake-env-secret", repr(snapshot))
        self.assertEqual(serialize_api_groups(settings), before)
        self.assertNotIn("fake-env-secret", before)

    def test_environment_does_not_override_stored_group(self):
        settings = settings_with((stored("saved"),))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake-env-secret"}):
            snapshot = resolve_api_request(settings)
        self.assertEqual(snapshot.api_key, "fake-saved")
        resolve_api_request(settings, environment=NeverReadEnvironment())

    def test_disabled_environment_reference_is_not_read(self):
        snapshot = resolve_api_request(settings_with((environment_key(enabled=False), stored("saved", 2))),
                                       environment=NeverReadEnvironment())
        self.assertEqual(snapshot.api_key, "fake-saved")

    def test_other_groups_keys_and_environment_are_never_used(self):
        settings = settings_with((stored("saved"),))
        other = APIGroup("other", "其他", "https://other.test/v1", "other-model", keys=(environment_key(),))
        snapshot = resolve_api_request(replace(settings, groups=(*settings.groups, other)), environment=NeverReadEnvironment())
        self.assertEqual(snapshot.api_key, "fake-saved")
        self.assertEqual(snapshot.model, "test-model")
        self.assertEqual(len(snapshot.candidates), 1)
        self.assert_error(replace(settings_with(), groups=(settings_with().groups[0], other)), "no_keys",
                          environment={"OPENAI_API_KEY": "fake-env-secret"})

    def test_none_mode_has_no_key_even_when_stored_and_environment_keys_exist(self):
        snapshot = resolve_api_request(settings_with((stored("saved"), environment_key()), auth_mode="none"),
                                       environment=NeverReadEnvironment())
        self.assertIsNone(snapshot.api_key)
        self.assertIsNone(snapshot.selected_key)
        self.assertEqual(snapshot.candidates, ())
        self.assertEqual(snapshot.auth_mode, "none")

    def test_none_mode_works_with_empty_key_list(self):
        snapshot = resolve_api_request(settings_with(auth_mode="none"))
        self.assertEqual(snapshot.model, "test-model")
        self.assertIsNone(snapshot.api_key)

    def test_snapshot_and_candidates_are_immutable(self):
        snapshot = resolve_api_request(settings_with((stored("one"),)))
        with self.assertRaises(FrozenInstanceError):
            snapshot.model = "changed"
        with self.assertRaises(FrozenInstanceError):
            snapshot.selected_key.key = "changed"

    def test_environment_and_settings_changes_do_not_mutate_existing_request(self):
        environment = {"OPENAI_API_KEY": "fake-original"}
        settings = settings_with((environment_key(),))
        first = resolve_api_request(settings, environment=environment)
        environment["OPENAI_API_KEY"] = "fake-new"
        settings = replace(settings, groups=(replace(settings.groups[0], model="new-model"),))
        second = resolve_api_request(settings, environment=environment)
        self.assertEqual((first.api_key, first.model), ("fake-original", "test-model"))
        self.assertEqual((second.api_key, second.model), ("fake-new", "new-model"))

    def test_explicit_temperature_override_does_not_modify_group(self):
        settings = settings_with((stored("one"),))
        snapshot = resolve_api_request(settings, temperature_override=0.2)
        self.assertEqual(snapshot.temperature, 0.2)
        self.assertEqual(settings.groups[0].temperature, 1.2)
        for value in (-1, 2.1, True, "0.7", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assert_error(settings, "invalid_temperature", temperature_override=value)

    def test_invalid_settings_and_blank_stored_keys_are_rejected_safely(self):
        settings = settings_with((stored("one"),))
        self.assert_error(replace(settings, active_group_id="missing"), "invalid_settings")
        blank = replace(settings.groups[0].keys[0], key=" ")
        self.assert_error(settings_with((blank,)), "invalid_settings")
        self.assert_error(replace(settings, schema_version=999), "invalid_settings")

    def test_read_saved_request_does_not_migrate_save_or_publish(self):
        store = Mock()
        settings = settings_with((stored("one"),))
        store.get_api_group_contents.return_value = serialize_api_groups(settings)
        publish = Mock()
        snapshot = APIGroupService(store, publish).resolve_request(environment={})
        self.assertEqual(snapshot.api_key, "fake-one")
        store.get_legacy_api_values.assert_not_called()
        store.save_api_group_contents.assert_not_called()
        publish.assert_not_called()

    def test_missing_saved_file_does_not_fall_back_to_old_settings(self):
        store = Mock()
        store.get_api_group_contents.return_value = None
        with self.assertRaises(APIGroupResolutionError) as raised:
            APIGroupService(store, Mock()).resolve_request()
        self.assertEqual(raised.exception.code, "not_configured")
        store.get_legacy_api_values.assert_not_called()
        store.save_api_group_contents.assert_not_called()


if __name__ == "__main__":
    unittest.main()
