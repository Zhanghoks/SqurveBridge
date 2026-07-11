from typing import Union, Dict, List, Optional
from pathlib import Path
from os import PathLike
import re
import unicodedata
import pandas as pd
from loguru import logger

from core.actor.reducer.BaseReduce import BaseReducer
from core.data_manage import Dataset, single_central_process
from core.utils import save_dataset


@BaseReducer.register_actor
class SEDEReducer(BaseReducer):
    """SEDE schema serialization reducer for BookSQL.

    Cleans the NL question and serializes the database schema into a
    natural-language string that is passed to SEDEGenerator as source_text.
    No LLM call — pure rule-based transformation.
    """

    NAME = "SEDEReducer"

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        use_schema: bool = True,
        add_column_types: bool = False,
        output_format: str = "json",
        save_dir: Optional[Union[str, PathLike]] = None,
        **kwargs,
    ):
        self.dataset = dataset
        self.use_schema = use_schema
        self.add_column_types = add_column_types
        self.output_format = output_format
        self.save_dir = save_dir

    @staticmethod
    def clean_str(text: str) -> str:
        """Normalize non-ASCII characters and collapse whitespace."""
        if not text:
            return ""
        text = unicodedata.normalize("NFKD", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def serialize_schema(self, schema: Union[Dict, List, pd.DataFrame]) -> str:
        """Serialize schema to natural-language string.

        Replaces <TAB>/<COL> T5 special tokens with readable delimiters.
        Output format: "Table: table_name | Columns: col1, col2, ..."
        """
        if isinstance(schema, pd.DataFrame):
            rows = schema.to_dict(orient="records")
        elif isinstance(schema, dict):
            rows = single_central_process(schema)
        else:
            rows = schema

        if not rows:
            return ""

        # Group columns by table
        tables: Dict[str, List[str]] = {}
        for row in rows:
            table = str(row.get("table_name", row.get("table", "")))
            col = str(row.get("column_name", row.get("column", "")))
            col_type = str(row.get("column_type", row.get("type", "")))
            if table not in tables:
                tables[table] = []
            if self.add_column_types and col_type:
                tables[table].append(f"{col} ({col_type})")
            else:
                tables[table].append(col)

        parts = []
        for table_name, cols in tables.items():
            parts.append(f"Table: {table_name} | Columns: {', '.join(cols)}")
        return "\n".join(parts)

    def act(self, item, schema: Union[Dict, List] = None, data_logger=None, **kwargs):
        if data_logger:
            data_logger.info(f"{self.NAME}.act start | item={item}")

        row = self.dataset[item]
        question = self.clean_str(row.get("question", ""))

        # Load schema
        if schema is None:
            schema = self.dataset.get_db_schema(item)

        schema_str = self.serialize_schema(schema) if self.use_schema else ""

        # Combine into source_text
        if schema_str:
            source_text = f"{question}\n\nSchema:\n{schema_str}"
        else:
            source_text = question

        # Store as instance_schemas
        result = {"source_text": source_text, "question": question, "schema_str": schema_str}

        if self.save_dir:
            instance_id = row.get("instance_id", str(item))
            save_path = Path(self.save_dir)
            if self.dataset and getattr(self.dataset, "dataset_index", None):
                save_path = save_path / str(self.dataset.dataset_index)
            save_path = save_path / f"{self.NAME}_{instance_id}.json"
            save_dataset(result, new_data_source=save_path)
            self.dataset.setitem(item, "instance_schemas", str(save_path))
        else:
            self.dataset.setitem(item, "instance_schemas", source_text)

        if data_logger:
            data_logger.info(f"{self.NAME}.act end | item={item}")
        return result
