"""Tools for listing, reading, and querying project data files."""

import csv
import json
import os
import sqlite3
from pathlib import Path

from tools import Tool


def get_data_dir():
    """Return the configured data directory."""
    return Path(
        os.environ.get("AGENTX_DATA_DIR", "data")
    ).resolve()


class ListFiles(Tool):
    name = "list_files"
    description = "List files in the configured data directory."
    args_doc = "{}"

    def execute(self, **kwargs):
        data_dir = get_data_dir()

        if not data_dir.is_dir():
            return f"ERROR: Data directory not found: {data_dir}"

        files = sorted(
            str(path.relative_to(data_dir))
            for path in data_dir.rglob("*")
            if path.is_file()
        )

        return json.dumps({"files": files})


class ReadFile(Tool):
    name = "read_file"
    description = "Read a text or CSV file from the data directory."
    args_doc = '{"filename": "scores.csv"}'

    def execute(self, filename="", **kwargs):
        data_dir = get_data_dir()
        path = (data_dir / filename).resolve()

        if not path.is_relative_to(data_dir):
            return "ERROR: File must be inside the data directory."

        if not path.is_file():
            return f"ERROR: File not found: {filename}"

        try:
            return path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            return f"ERROR: Could not read file: {exc}"


class SQLQuery(Tool):
    name = "sql_query"
    description = (
        "Run a read-only SELECT query on a CSV file. "
        "The CSV data is available as a table named data."
    )
    args_doc = (
        '{"filename": "scores.csv", '
        '"sql": "SELECT topic FROM data WHERE score < 40"}'
    )

    @staticmethod
    def _is_number(value):
        """Check whether a nonempty value can be parsed as a number."""
        if value is None or str(value).strip() == "":
            return False

        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

    def execute(self, filename="", sql="", **kwargs):
        data_dir = get_data_dir()
        path = (data_dir / filename).resolve()

        if not path.is_relative_to(data_dir):
            return "ERROR: File must be inside the data directory."

        if not path.is_file():
            return f"ERROR: File not found: {filename}"

        if path.suffix.lower() != ".csv":
            return "ERROR: SQL queries are supported only for CSV files."

        # Permit read-only SELECT statements only.
        if not sql.strip().lower().startswith("select "):
            return "ERROR: Only SELECT queries are allowed."

        try:
            with path.open(
                "r",
                newline="",
                encoding="utf-8-sig",
            ) as file:
                reader = csv.DictReader(file)
                columns = reader.fieldnames
                rows = list(reader)

            if not columns:
                return "ERROR: CSV file has no header row."

            if not rows:
                return "No data rows found in CSV."

            # Infer numeric columns so comparisons such as score < 40
            # work numerically instead of comparing text values.
            column_definitions = []

            for column in columns:
                escaped_column = '"' + column.replace('"', '""') + '"'

                nonempty_values = [
                    row.get(column, "").strip()
                    for row in rows
                    if row.get(column, "").strip() != ""
                ]

                is_numeric = (
                    bool(nonempty_values)
                    and all(
                        self._is_number(value)
                        for value in nonempty_values
                    )
                )

                sql_type = "REAL" if is_numeric else "TEXT"
                column_definitions.append(
                    f"{escaped_column} {sql_type}"
                )

            with sqlite3.connect(":memory:") as connection:
                connection.execute(
                    "CREATE TABLE data ("
                    + ", ".join(column_definitions)
                    + ")"
                )

                escaped_columns = [
                    '"' + column.replace('"', '""') + '"'
                    for column in columns
                ]

                placeholders = ", ".join("?" for _ in columns)

                insert_sql = (
                    "INSERT INTO data ("
                    + ", ".join(escaped_columns)
                    + f") VALUES ({placeholders})"
                )

                values = []

                for row in rows:
                    converted_row = []

                    for column in columns:
                        value = row.get(column, "")

                        nonempty_values = [
                            item.get(column, "").strip()
                            for item in rows
                            if item.get(column, "").strip() != ""
                        ]

                        is_numeric = (
                            bool(nonempty_values)
                            and all(
                                self._is_number(item)
                                for item in nonempty_values
                            )
                        )

                        if is_numeric:
                            converted_row.append(
                                float(value) if value.strip() else None
                            )
                        else:
                            converted_row.append(value)

                    values.append(tuple(converted_row))

                connection.executemany(insert_sql, values)

                cursor = connection.execute(sql)
                result_rows = cursor.fetchall()
                result_columns = [
                    description[0]
                    for description in cursor.description
                ]

                return json.dumps({
                    "columns": result_columns,
                    "rows": result_rows,
                })

        except (OSError, csv.Error, sqlite3.Error, ValueError) as exc:
            return f"ERROR: Query failed: {exc}"