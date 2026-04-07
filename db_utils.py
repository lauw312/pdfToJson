from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import pymysql
except ModuleNotFoundError:  # pragma: no cover - optional until DB dependency is installed
    pymysql = None


DB_PROFILES_PATH = Path(__file__).resolve().with_name("db_profiles.json")


DB_FIELD_NAMES = [
    "host",
    "port",
    "user",
    "password",
    "database",
    "main_table",
    "detail_table",
    "main_key_column",
    "detail_foreign_key",
]

MAIN_AUTO_INCREMENT_COLUMNS = {"INSP_ID"}
DETAIL_AUTO_INCREMENT_COLUMNS = {"INSP_DTL_ID"}


DEFAULT_DB_CONFIG = {
    "host": "",
    "port": 3306,
    "user": "",
    "password": "",
    "database": "",
    "main_table": "INSP_HDR",
    "detail_table": "INSP_DTL",
    "main_key_column": "INSP_ID",
    "detail_foreign_key": "INSP_ID",
}


def normalize_editor_value(value: Any) -> Any:
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except ModuleNotFoundError:
        pass
    except TypeError:
        pass
    except ValueError:
        pass
    return value


def normalize_record_values(record: dict[str, Any]) -> dict[str, Any]:
    return {key: normalize_editor_value(value) for key, value in record.items()}


def validate_sql_identifier(name: str, label: str) -> str:
    candidate = str(name).strip()
    if not candidate or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
        raise ValueError(f"{label} 값이 올바르지 않습니다: {name}")
    return candidate


def quote_identifier(name: str, label: str) -> str:
    return f"`{validate_sql_identifier(name, label)}`"


def build_upsert_query(table_name: str, data: dict[str, Any], key_column: str) -> tuple[str, list[Any]]:
    if not data:
        raise ValueError("저장할 데이터가 없습니다.")

    columns = list(data.keys())
    column_clause = ", ".join(quote_identifier(column, "컬럼명") for column in columns)
    values_clause = ", ".join(["%s"] * len(columns))
    quoted_table = quote_identifier(table_name, "테이블명")
    quoted_key = quote_identifier(key_column, "기본 키 컬럼")

    updatable_columns = [column for column in columns if column != key_column]
    if updatable_columns:
        update_clause = ", ".join(
            f"{quote_identifier(column, '컬럼명')} = VALUES({quote_identifier(column, '컬럼명')})"
            for column in updatable_columns
        )
    else:
        update_clause = f"{quoted_key} = VALUES({quoted_key})"

    query = (
        f"INSERT INTO {quoted_table} ({column_clause}) "
        f"VALUES ({values_clause}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )
    return query, [data[column] for column in columns]


def normalize_db_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(DEFAULT_DB_CONFIG)
    normalized.update({key: config.get(key) for key in DB_FIELD_NAMES if key in config})
    normalized["host"] = str(normalized["host"] or "").strip()
    normalized["port"] = int(normalized.get("port") or 3306)
    normalized["user"] = str(normalized["user"] or "").strip()
    normalized["password"] = "" if normalized["password"] is None else str(normalized["password"])
    normalized["database"] = str(normalized["database"] or "").strip()
    normalized["main_table"] = str(normalized["main_table"] or "").strip()
    normalized["detail_table"] = str(normalized["detail_table"] or "").strip()
    normalized["main_key_column"] = str(normalized["main_key_column"] or "INSP_ID").strip() or "INSP_ID"
    normalized["detail_foreign_key"] = str(normalized["detail_foreign_key"] or "INSP_ID").strip() or "INSP_ID"
    return normalized


def load_db_profiles() -> dict[str, dict[str, Any]]:
    if not DB_PROFILES_PATH.exists():
        return {}

    raw = json.loads(DB_PROFILES_PATH.read_text(encoding="utf-8"))
    profiles: dict[str, dict[str, Any]] = {}
    for name, config in raw.items():
        if not isinstance(name, str) or not isinstance(config, dict):
            continue
        profiles[name] = normalize_db_config(config)
    return profiles


def save_db_profile(profile_name: str, config: dict[str, Any]) -> None:
    name = str(profile_name).strip()
    if not name:
        raise ValueError("프로필명을 입력해 주세요.")

    profiles = load_db_profiles()
    profiles[name] = normalize_db_config(config)
    DB_PROFILES_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_db_profile(profile_name: str) -> None:
    name = str(profile_name).strip()
    if not name:
        raise ValueError("삭제할 프로필명이 없습니다.")

    profiles = load_db_profiles()
    if name not in profiles:
        raise ValueError("선택한 프로필을 찾을 수 없습니다.")

    del profiles[name]
    DB_PROFILES_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")


def is_db_configured(db_config: dict[str, Any]) -> bool:
    required_fields = ["host", "user", "database", "main_table", "detail_table"]
    return all(str(db_config.get(field, "")).strip() for field in required_fields)


def table_exists(cursor: Any, table_name: str) -> bool:
    cursor.execute("SHOW TABLES LIKE %s", (table_name,))
    return cursor.fetchone() is not None


def validate_target_tables(cursor: Any, db_config: dict[str, Any]) -> None:
    missing_tables = [
        table_name
        for table_name in [db_config["main_table"], db_config["detail_table"]]
        if not table_exists(cursor, table_name)
    ]
    if missing_tables:
        missing = ", ".join(missing_tables)
        raise ValueError(
            f"MariaDB 테이블이 없습니다: {missing}. 사이드바에서 Main Table / Detail Table 값을 확인해 주세요."
        )


def test_mariadb_connection(db_config: dict[str, Any]) -> str:
    if pymysql is None:
        raise RuntimeError("PyMySQL이 설치되어 있지 않습니다. `pip install -r requirements.txt`를 먼저 실행해 주세요.")

    normalized_config = normalize_db_config(db_config)
    required_fields = ["host", "user", "database"]
    if not all(str(normalized_config.get(field, "")).strip() for field in required_fields):
        raise ValueError("Host, User, Database를 입력한 뒤 연결 테스트를 실행해 주세요.")

    connection = pymysql.connect(
        host=normalized_config["host"],
        port=int(normalized_config["port"]),
        user=normalized_config["user"],
        password=normalized_config["password"],
        database=normalized_config["database"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if not row or row[0] != 1:
                raise RuntimeError("DB 연결은 되었지만 기본 쿼리 확인에 실패했습니다.")
            validate_target_tables(cursor, normalized_config)
    finally:
        connection.close()

    return "MariaDB 연결과 대상 테이블 확인이 완료되었습니다."


def save_result_to_mariadb(
    result: dict[str, Any],
    db_config: dict[str, Any],
    sanitize_detail_rows: Any,
) -> None:
    if pymysql is None:
        raise RuntimeError("PyMySQL이 설치되어 있지 않습니다. `pip install -r requirements.txt`를 먼저 실행해 주세요.")

    normalized_config = normalize_db_config(db_config)
    if not is_db_configured(normalized_config):
        raise ValueError("MariaDB 저장 설정이 비어 있습니다. 사이드바에서 접속 정보와 테이블명을 입력해 주세요.")

    main_data = normalize_record_values(dict(result.get("main", {})))
    detail_rows = [
        normalize_record_values(dict(row))
        for row in sanitize_detail_rows(list(result.get("detail", [])))
    ]
    if not main_data:
        raise ValueError("main 데이터가 없어 저장할 수 없습니다.")

    main_key_column = validate_sql_identifier(normalized_config["main_key_column"], "main 키 컬럼")
    detail_foreign_key = validate_sql_identifier(normalized_config["detail_foreign_key"], "detail 외래 키 컬럼")
    raw_main_key_value = main_data.get(main_key_column)
    main_key_value = None if raw_main_key_value in ("", None) else raw_main_key_value

    connection = pymysql.connect(
        host=normalized_config["host"],
        port=int(normalized_config["port"]),
        user=normalized_config["user"],
        password=normalized_config["password"],
        database=normalized_config["database"],
        charset="utf8mb4",
        autocommit=False,
    )

    try:
        with connection.cursor() as cursor:
            validate_target_tables(cursor, normalized_config)

            if main_key_column in MAIN_AUTO_INCREMENT_COLUMNS:
                filtered_main_data = {
                    key: value
                    for key, value in main_data.items()
                    if key not in MAIN_AUTO_INCREMENT_COLUMNS
                }
                if not filtered_main_data:
                    raise ValueError("main 저장 대상 컬럼이 없습니다.")

                insert_columns = list(filtered_main_data.keys())
                insert_query = (
                    f"INSERT INTO {quote_identifier(normalized_config['main_table'], 'main 테이블명')} "
                    f"({', '.join(quote_identifier(column, '컬럼명') for column in insert_columns)}) "
                    f"VALUES ({', '.join(['%s'] * len(insert_columns))})"
                )
                cursor.execute(insert_query, [filtered_main_data[column] for column in insert_columns])
                main_key_value = cursor.lastrowid
            else:
                main_query, main_params = build_upsert_query(
                    normalized_config["main_table"],
                    main_data,
                    main_key_column,
                )
                cursor.execute(main_query, main_params)
                if main_key_value is None:
                    main_key_value = cursor.lastrowid

            if main_key_value in ("", None):
                raise ValueError(f"main 데이터의 {main_key_column} 값을 확인할 수 없습니다.")

            if main_key_column not in MAIN_AUTO_INCREMENT_COLUMNS:
                delete_query = (
                    f"DELETE FROM {quote_identifier(normalized_config['detail_table'], 'detail 테이블명')} "
                    f"WHERE {quote_identifier(detail_foreign_key, 'detail 외래 키 컬럼')} = %s"
                )
                cursor.execute(delete_query, (main_key_value,))

            for detail_row in detail_rows:
                filtered_detail_row = {
                    key: value
                    for key, value in detail_row.items()
                    if key not in DETAIL_AUTO_INCREMENT_COLUMNS
                }
                filtered_detail_row[detail_foreign_key] = main_key_value
                insert_columns = list(filtered_detail_row.keys())
                insert_query = (
                    f"INSERT INTO {quote_identifier(normalized_config['detail_table'], 'detail 테이블명')} "
                    f"({', '.join(quote_identifier(column, '컬럼명') for column in insert_columns)}) "
                    f"VALUES ({', '.join(['%s'] * len(insert_columns))})"
                )
                cursor.execute(insert_query, [filtered_detail_row[column] for column in insert_columns])

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
