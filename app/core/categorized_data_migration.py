"""One-time, non-destructive move into the three existing data folders."""
import configparser
import io
import json
from pathlib import Path

from app.core.dotenv_file import DotEnvFile
from app.core.paths import ProjectPaths
from app.settings.api_groups import deserialize_api_groups, migrate_legacy_api, serialize_api_groups
from app.settings.env_group_storage import prepare_env_groups
from app.settings.tool_settings import prepare_tool_settings_v2


class CategorizedDataMigrationError(ValueError):
    pass


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeError):
        raise CategorizedDataMigrationError(f"來源檔無法讀取：{path.name}。原資料未修改。") from None


def _read_json(path: Path, expected_type: type):
    try:
        payload = json.loads(_read_text(path))
    except (ValueError, RecursionError):
        raise CategorizedDataMigrationError(f"來源檔格式無效：{path.name}。原資料未修改。") from None
    if type(payload) is not expected_type:
        raise CategorizedDataMigrationError(f"來源檔格式無效：{path.name}。原資料未修改。")
    return payload


def prepare_categorized_data(paths: ProjectPaths) -> tuple[dict[Path, str], dict[Path, bytes]]:
    """Validate sources and return destination text without writing anything."""
    if not paths.categorized_data:
        raise CategorizedDataMigrationError("目的路徑未啟用分類設定。")
    old = ProjectPaths(paths.project_root, paths.runtime_root)
    pairs = (
        (old.app_ini, paths.app_ini),
        (old.prompt_json, paths.prompt_json),
        (old.api_groups_json, paths.api_groups_json),
        (old.tools_json, paths.tools_json),
        (old.preferences_json, paths.preferences_json),
        (old.apps_json, paths.apps_json),
    )
    targets = [destination for _, destination in pairs] + [paths.env_file]
    for destination in targets:
        if destination.exists():
            raise CategorizedDataMigrationError(f"目的檔已存在：{destination.name}。原資料未修改。")

    originals = {}
    for source, _ in pairs:
        try:
            originals[source] = source.read_bytes()
        except OSError:
            raise CategorizedDataMigrationError(f"來源檔無法讀取：{source.name}。原資料未修改。") from None
    for unchanged in (old.history_json, old.memory_json, old.legacy_api_ini):
        try:
            originals[unchanged] = unchanged.read_bytes()
        except OSError:
            raise CategorizedDataMigrationError(f"來源檔無法讀取：{unchanged.name}。原資料未修改。") from None
    if old.env_file.exists():
        originals[old.env_file] = old.env_file.read_bytes()

    try:
        parser = configparser.ConfigParser()
        parser.read_file(io.StringIO(_read_text(old.app_ini)))
        if not parser.has_section("General"):
            raise ValueError()
        legacy_api = configparser.ConfigParser()
        legacy_api.read_file(io.StringIO(_read_text(old.legacy_api_ini)))
        if not legacy_api.has_section("API"):
            raise ValueError()
    except (configparser.Error, ValueError):
        raise CategorizedDataMigrationError("INI 來源格式無效；原資料未修改。") from None

    _read_json(old.prompt_json, dict)
    _read_json(old.preferences_json, dict)
    _read_json(old.apps_json, list)
    _read_json(old.history_json, list)
    _read_json(old.memory_json, dict)
    try:
        groups = deserialize_api_groups(_read_text(old.api_groups_json))
        if groups.schema_version != 1:
            raise ValueError()
        legacy_groups = migrate_legacy_api(dict(legacy_api.items("API", raw=True)))
        current_keys = {key.key for group in groups.groups for key in group.keys if key.source == "stored"}
        legacy_keys = {key.key for group in legacy_groups.groups for key in group.keys if key.source == "stored"}
        if not legacy_keys.issubset(current_keys):
            raise CategorizedDataMigrationError("舊 API 設定有未納入群組的金鑰；原資料未修改。")
        new_groups, group_updates, _ = prepare_env_groups(groups, None)
        new_tool_text, tool_updates, _ = prepare_tool_settings_v2(_read_json(old.tools_json, dict))
        duplicate_names = set(group_updates) & set(tool_updates)
        if duplicate_names:
            raise CategorizedDataMigrationError("金鑰環境變數名稱衝突；原資料未修改。")
        env_text = DotEnvFile(old.env_file).render_updates({**group_updates, **tool_updates})
    except CategorizedDataMigrationError:
        raise
    except (ValueError, TypeError, UnicodeError):
        raise CategorizedDataMigrationError("金鑰來源格式無效；原資料未修改。") from None

    contents = {
        paths.app_ini: _read_text(old.app_ini),
        paths.prompt_json: _read_text(old.prompt_json),
        paths.api_groups_json: serialize_api_groups(new_groups),
        paths.tools_json: new_tool_text,
        paths.preferences_json: _read_text(old.preferences_json),
        paths.apps_json: _read_text(old.apps_json),
        paths.env_file: env_text,
    }
    return contents, originals


def migrate_categorized_data(paths: ProjectPaths) -> tuple[str, ...]:
    """Write only new destinations, verify them, and keep every old file."""
    from app.core.config_manager import write_text_bundle_atomically

    contents, originals = prepare_categorized_data(paths)
    if any(path.exists() for path in contents):
        raise CategorizedDataMigrationError("目的檔已存在；原資料未修改。")
    if any(path.read_bytes() != value for path, value in originals.items()):
        raise CategorizedDataMigrationError("來源檔在準備期間變動；未寫入目的檔。")
    write_text_bundle_atomically(contents)
    try:
        if any(path.read_bytes() != text.encode("utf-8") for path, text in contents.items()):
            raise CategorizedDataMigrationError("新檔寫入後核對失敗；尚未切換讀寫。")
        if any(path.read_bytes() != value for path, value in originals.items()):
            raise CategorizedDataMigrationError("舊檔在轉換期間變動；尚未切換讀寫。")
    except OSError:
        raise CategorizedDataMigrationError("新檔無法核對；尚未切換讀寫。") from None
    return tuple(str(path.relative_to(paths.project_root)) for path in contents)
