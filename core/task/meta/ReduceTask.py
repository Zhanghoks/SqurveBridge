import warnings
from os import PathLike
from typing import Union, List, Optional
from llama_index.core.llms.llm import LLM

from core.task.meta.MetaTask import MetaTask
from core.actor.reducer.LinkAlignReduce import LinkAlignReducer
from core.actor.reducer.BaseReduce import BaseReducer
from core.actor.reducer import FINSQLReducer, C3SQLReducer, RESDSQLReducer, RESDSQLBooksqlReducer

try:
    from core.actor.reducer.SEDEReduce import SEDEReducer
except Exception:
    SEDEReducer = None

try:
    from core.actor.reducer.UNISARBooksqlReduce import UNISARBooksqlReducer
except Exception:
    UNISARBooksqlReducer = None

try:
    from core.actor.reducer.DINSQLBooksqlReduce import DINSQLBooksqlReducer
except Exception:
    DINSQLBooksqlReducer = None


class ReduceTask(MetaTask):
    """ Task For Text-to-SQL """

    NAME = "ReduceTask"
    registered_reduce_type = ["LinkAlignReducer", "LinkAlign", "FINSQLReducer", "FINSQL", "C3SQLReducer", "C3SQL", "SEDEReducer", "SEDE", "RESDSQLReducer", "RESDSQL", "RESDSQLBooksqlReducer", "RESDSQLBooksql", "UNISARBooksqlReducer", "UNISARBooksql", "DINSQLBooksqlReducer", "DINSQLBooksql"]

    def __init__(
            self,
            llm: Union[LLM, List[LLM]],
            reduce_type: str = "LinkAlignReducer",
            output_format: str = "str",  # output in `list` or `str`
            save_dir: Union[str, PathLike] = "../files/instance_schemas",
            **kwargs
    ):
        self.llm: Union[LLM, List[LLM]] = llm
        self.reduce_type: str = reduce_type
        self.output_format: str = output_format
        self.save_dir: Union[str, PathLike] = save_dir

        super().__init__(**kwargs)

    def load_actor(self, actor_type: str = None, **kwargs) -> Optional[BaseReducer]:

        if actor_type is None:
            actor_type = self.reduce_type

        output_format = self.output_format
        if "output_format" in kwargs:
            output_format = kwargs.get("output_format")

        is_save = self.is_save
        if "is_save" in kwargs:
            is_save = kwargs.get("is_save")

        save_dir = self.save_dir
        if "save_dir" in kwargs:
            save_dir = kwargs.get("save_dir")

        reduce_args = {
            "dataset": self.dataset,
            "llm": self.llm,
            # The arguments below can be replaced by the one provided in `actor_args`.
            "output_format": output_format,
            "is_save": is_save,
            "save_dir": save_dir,
        }
        for key, val in kwargs.items():
            reduce_args[key] = val

        if hasattr(self, "actor"):
            actor = self.actor.copy_instance()
            if actor and isinstance(actor, BaseReducer):
                actor.dataset = self.dataset
                actor.llm = self.llm
                for key, val in kwargs.items():
                    setattr(actor, key, val)
                return actor

        if actor_type in ("LinkAlignReducer", "LinkAlign"):
            actor = LinkAlignReducer(**reduce_args)
            return actor

        elif actor_type in ("FINSQLReducer", "FINSQL") and FINSQLReducer:
            actor = FINSQLReducer(**reduce_args)
            return actor

        elif actor_type in ("C3SQLReducer", "C3SQL") and C3SQLReducer:
            actor = C3SQLReducer(**reduce_args)
            return actor

        elif actor_type in ("SEDEReducer", "SEDE") and SEDEReducer:
            actor = SEDEReducer(**reduce_args)
            return actor

        elif actor_type in ("RESDSQLReducer", "RESDSQL") and RESDSQLReducer:
            actor = RESDSQLReducer(**reduce_args)
            return actor

        elif actor_type in ("RESDSQLBooksqlReducer", "RESDSQLBooksql") and RESDSQLBooksqlReducer:
            actor = RESDSQLBooksqlReducer(**reduce_args)
            return actor

        elif actor_type in ("UNISARBooksqlReducer", "UNISARBooksql") and UNISARBooksqlReducer:
            actor = UNISARBooksqlReducer(**reduce_args)
            return actor

        elif actor_type in ("DINSQLBooksqlReducer", "DINSQLBooksql") and DINSQLBooksqlReducer:
            actor = DINSQLBooksqlReducer(**reduce_args)
            return actor

        warnings.warn(f"The reduce_type `{actor_type}` is not available.", category=UserWarning)
        return None
