"""Editable settings transaction, independent of the view."""
import os
from dataclasses import replace

from app.settings.api_group_service import APIGroupService
from app.settings.api_groups import APIGroupSettings, ENV_SCHEMA_VERSION, migrate_legacy_api, validate_api_groups
from app.settings.editing import normalize_group_input, normalize_key_entries, validate_group_draft
from app.settings.model import SettingsValidationError
from app.settings.service import settings_service


class SettingsSession:
    def __init__(self, settings_backend=None, group_backend=None):
        self.backend = settings_service if settings_backend is None else settings_backend
        self.group_backend = (APIGroupService(self.backend.store)
                              if group_backend is None and settings_backend is None else group_backend)
        self.reload()

    @property
    def group_mode(self):
        return self.group_backend is not None

    @property
    def is_dirty(self):
        return self.snapshot != self.original_snapshot or self.groups != self.original_groups

    def _read_groups(self):
        if not self.group_mode:
            return APIGroupSettings(), None
        try:
            groups = self.group_backend.load()
            if groups is None:
                if getattr(self.group_backend.store, "categorized_data", False) is True:
                    groups = APIGroupSettings(schema_version=ENV_SCHEMA_VERSION)
                else:
                    # Preview migration only: cancel must never create a file.
                    groups = migrate_legacy_api(
                        self.group_backend.store.get_legacy_api_values(),
                        bool(os.environ.get("OPENAI_API_KEY", "").strip()),
                    )
            return groups, None
        except SettingsValidationError as error:
            return APIGroupSettings(), str(error)

    def reload(self):
        snapshot = self.backend.load()
        groups, error = self._read_groups()
        self.original_snapshot = self.snapshot = snapshot
        self.original_groups = self.groups = groups
        self.group_error = error

    def update(self, values):
        values = dict(values)
        if self.group_mode:
            for field in ("api_keys", "base_url", "model", "temperature"):
                values.pop(field, None)
        if "api_keys" in values:
            values["api_keys"] = normalize_key_entries(values["api_keys"])
        self.snapshot = replace(self.snapshot, **values)

    def update_groups(self, groups):
        if self.group_error is None:
            self.groups = normalize_group_input(groups)

    def apply(self):
        if self.group_mode:
            validate_group_draft(self.groups)
        if self.groups != self.original_groups:
            validate_api_groups(self.groups)
            saved = self.backend.save(self.snapshot, api_groups=self.groups, group_settings_mode=True)
            if self.groups.schema_version == ENV_SCHEMA_VERSION:
                self.groups = self.group_backend.load()
        else:
            options = {"group_settings_mode": True} if self.group_mode else {}
            saved = self.backend.save(self.snapshot, **options)
        # Advance the baseline only after the entire bundle has been saved.
        self.original_snapshot = self.snapshot = saved
        self.original_groups = self.groups

    def discard(self):
        self.snapshot = self.original_snapshot
        self.groups = self.original_groups

    def clear_history(self):
        self.backend.clear_history()
