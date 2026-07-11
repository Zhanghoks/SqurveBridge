import warnings
from os import PathLike
from typing import Union, List, Optional
from llama_index.core.llms.llm import LLM

from core.task.meta.MetaTask import MetaTask
from core.actor.generator import (
    BaseGenerator,
    LinkAlignGenerator,
    DINSQLGenerator,
    DAILSQLGenerate,
    CHESSGenerator,
    MACSQLGenerator,
    RSLSQLGenerator,
    ReFoRCEGenerator,
    OpenSearchSQLGenerator,
    RecursiveGenerator,
    FINSQLGenerator,
    C3SQLGenerator,
    RESDSQLGenerator,
    RESDSQLBooksqlGenerator,
)

try:
    from core.actor.generator.SEDEGenerate import SEDEGenerator
except Exception:
    SEDEGenerator = None

try:
    from core.actor.generator.UNISARBooksqlGenerate import UNISARBooksqlGenerator
except Exception:
    UNISARBooksqlGenerator = None

try:
    from core.actor.generator.DINSQLBooksqlGenerate import DINSQLBooksqlGenerator
except Exception:
    DINSQLBooksqlGenerator = None

try:
    from core.actor.generator.ESQLGenerate import ESQLGenerator
except Exception:
    ESQLGenerator = None

try:
    from core.actor.generator.EHRGenerate import EHRGenerator
except Exception:
    EHRGenerator = None


class GenerateTask(MetaTask):
    """ Task For Text-to-SQL """

    NAME = "GenerateTask"
    registered_generate_type = [
        "LinkAlignGenerator", "LinkAlign",
        "DIN_SQLGenerator", "DIN_SQL",
        "DAILSQLGenerator", "DAILSQL",
        "FINSQLGenerator", "FINSQL",
        "C3SQLGenerator", "C3SQL",
        "SEDEGenerator", "SEDE",
        "RESDSQLGenerator", "RESDSQL",
        "RESDSQLBooksqlGenerator", "RESDSQLBooksql",
        "UNISARBooksqlGenerator", "UNISARBooksql",
        "DINSQLBooksqlGenerator", "DINSQLBooksql",
        "ESQLGenerator", "ESQL",
        "EHRGenerator", "EHR",
    ]

    def __init__(
            self,
            llm: Union[LLM, List[LLM]],
            generate_type: str = "LinkAlignGenerator",
            save_dir: Union[str, PathLike] = "../files/pred_sql",
            **kwargs
    ):
        self.llm: Union[LLM, List[LLM]] = llm
        self.generate_type: str = generate_type
        self.save_dir: Union[str, PathLike] = save_dir

        super().__init__(**kwargs)

    def load_actor(self, actor_type: str = None, **kwargs) -> Optional[BaseGenerator]:
        if actor_type is None:
            actor_type = self.generate_type

        is_save = self.is_save
        if "is_save" in kwargs:
            is_save = kwargs.get("is_save")

        save_dir = self.save_dir
        if "save_dir" in kwargs:
            save_dir = kwargs.get("save_dir")

        generate_args = {
            "dataset": self.dataset,
            "llm": self.llm,
            # The arguments below can be replaced by the one provided in `actor_args`.
            "is_save": is_save,
            "save_dir": save_dir,
        }
        for key, val in kwargs.items():
            generate_args[key] = val

        if hasattr(self, "actor"):
            actor = self.actor.copy_instance()
            if actor and isinstance(actor, BaseGenerator):
                actor.dataset = self.dataset
                actor.llm = self.llm
                for key, val in kwargs.items():
                    setattr(actor, key, val)
                return actor

        if actor_type in ("LinkAlignGenerator", "LinkAlign") and LinkAlignGenerator:
            actor = LinkAlignGenerator(**generate_args)
            return actor

        elif actor_type in ("DINSQLGenerator", "DINSQL") and DINSQLGenerator:
            actor = DINSQLGenerator(**generate_args)
            return actor

        elif actor_type in ("DAILSQLGenerator", "DAILSQL") and DAILSQLGenerate:
            actor = DAILSQLGenerate(**generate_args)
            return actor

        elif actor_type in ("CHESSGenerator", "CHESS") and CHESSGenerator:
            actor = CHESSGenerator(**generate_args)
            return actor

        elif actor_type in ("MACSQLGenerator", "MACSQL") and MACSQLGenerator:
            actor = MACSQLGenerator(**generate_args)
            return actor

        elif actor_type in ("RSLSQLGenerator", "RSLSQL") and RSLSQLGenerator:
            actor = RSLSQLGenerator(**generate_args)
            return actor

        elif actor_type in ("ReFoRCEGenerator", "ReFoRCE") and ReFoRCEGenerator:
            actor = ReFoRCEGenerator(**generate_args)
            return actor

        elif actor_type in ("OpenSearchSQLGenerator", "OpenSearchSQL") and OpenSearchSQLGenerator:
            actor = OpenSearchSQLGenerator(**generate_args)
            return actor

        elif actor_type in ("RecursiveGenerator", "Recursive") and RecursiveGenerator:
            actor = RecursiveGenerator(**generate_args)
            return actor

        elif actor_type in ("FINSQLGenerator", "FINSQL") and FINSQLGenerator:
            actor = FINSQLGenerator(**generate_args)
            return actor

        elif actor_type in ("C3SQLGenerator", "C3SQL") and C3SQLGenerator:
            actor = C3SQLGenerator(**generate_args)
            return actor

        elif actor_type in ("SEDEGenerator", "SEDE") and SEDEGenerator:
            actor = SEDEGenerator(**generate_args)
            return actor

        elif actor_type in ("RESDSQLGenerator", "RESDSQL") and RESDSQLGenerator:
            actor = RESDSQLGenerator(**generate_args)
            return actor

        elif actor_type in ("RESDSQLBooksqlGenerator", "RESDSQLBooksql") and RESDSQLBooksqlGenerator:
            actor = RESDSQLBooksqlGenerator(**generate_args)
            return actor

        elif actor_type in ("UNISARBooksqlGenerator", "UNISARBooksql") and UNISARBooksqlGenerator:
            actor = UNISARBooksqlGenerator(**generate_args)
            return actor

        elif actor_type in ("DINSQLBooksqlGenerator", "DINSQLBooksql") and DINSQLBooksqlGenerator:
            actor = DINSQLBooksqlGenerator(**generate_args)
            return actor

        elif actor_type in ("ESQLGenerator", "ESQL") and ESQLGenerator:
            actor = ESQLGenerator(**generate_args)
            return actor

        elif actor_type in ("EHRGenerator", "EHR") and EHRGenerator:
            actor = EHRGenerator(**generate_args)
            return actor

        warnings.warn(f"The generate_type `{actor_type}` is not available.", category=UserWarning)
        return None
