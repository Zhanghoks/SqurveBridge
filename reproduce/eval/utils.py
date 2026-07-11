import copy
from typing import Union
from core.base import Router
from core.engine import Engine
from core.evaluate import Evaluator
from core.utils import load_dataset
from pathlib import Path
from loguru import logger
from reproduce.metrics.diagnostics import evaluate_execution_detail

# For default config, we use `generate` for task id
GENERATE_TASK_ID = "generate"
USE_PARALLEL = True


def should_use_process_parallel(generate_num: int) -> bool:
    return USE_PARALLEL and generate_num > 1


def resolve_saved_dataset_path(path: Union[str, Path]) -> Path:
    path = Path(path)
    if path.exists():
        return path
    stem = path.stem
    # 精确匹配回退：仅接受 stem 本身或 "stem_*" 派生（避免 task_1 误匹配 task_10）
    candidates = [
        p for p in sorted(path.parent.glob(stem + "*.json"))
        if p.stem == stem or p.stem.startswith(stem + "_")
    ]
    if candidates:
        return candidates[0]
    return path


def load_router(config_path: str = None, identifier: str = None, config: dict = None):
    if config is not None:
        original_config = copy.deepcopy(config)
    else:
        original_config = load_dataset(config_path)

    dataset_save_dir = original_config.pop("dataset_save_dir")
    sql_save_dir = original_config.pop("sql_save_dir")
    n = original_config.pop("generate_num")

    # make sure the dir exists
    Path(dataset_save_dir).mkdir(parents=True, exist_ok=True)
    Path(sql_save_dir).mkdir(parents=True, exist_ok=True)

    Router._sys_config_path = "../config/sys_config.json"
    router = Router()
    router.init_config(original_config)
    task_lis, cpx_task_lis, exec_process, save_lis = expand_execution_graph(
        task_meta=router.task_meta,
        cpx_task_meta=router.cpx_task_meta,
        exec_process=router.exec_process,
        iterations=n,
        dataset_save_dir=dataset_save_dir,
        sql_save_dir=sql_save_dir,
        identifier=identifier,
    )
    router._task_meta = task_lis
    router._cpx_task_meta = cpx_task_lis
    router._exec_process = exec_process

    return router, save_lis


def _suffix_task_refs(task_lis, suffix):
    """Suffix task IDs in a complex task's nested task list."""
    if isinstance(task_lis, str):
        return f"{task_lis}{suffix}"
    return [_suffix_task_refs(item, suffix) for item in task_lis]


def expand_execution_graph(
        task_meta,
        cpx_task_meta,
        exec_process,
        iterations,
        dataset_save_dir,
        sql_save_dir,
        identifier,
):
    """Clone the configured execution graph for independent reproduce runs."""
    task_meta = list(task_meta or [])
    cpx_task_meta = list(cpx_task_meta or [])
    process_ids = [item for item in (exec_process or []) if item != "~p"]
    task_ids = {task["task_id"] for task in task_meta}
    cpx_ids = {task["task_id"] for task in cpx_task_meta}

    if not process_ids:
        process_ids = [GENERATE_TASK_ID] if GENERATE_TASK_ID in task_ids else []
    unknown = [item for item in process_ids if item not in task_ids | cpx_ids]
    if unknown:
        raise ValueError(f"Unknown reproduce execution task(s): {', '.join(unknown)}")

    cloned_tasks = []
    cloned_complex_tasks = []
    cloned_process = []
    save_paths = []

    for iteration in range(1, iterations + 1):
        suffix = str(iteration)
        save_path = None
        if identifier is not None:
            save_path = dataset_save_dir + f"{identifier}/task_{iteration}.json"

        for original in task_meta:
            task = copy.deepcopy(original)
            task["task_id"] = f"{original['task_id']}{suffix}"
            if original.get("dataset_save_path"):
                p = Path(task["dataset_save_path"])
                task["dataset_save_path"] = str(p.with_name(f"{p.stem}{suffix}{p.suffix}"))
            actor_meta = task.setdefault("meta", {}).setdefault("actor", {})
            if identifier is not None and actor_meta.get("save_dir"):
                actor_meta["save_dir"] = str(Path(actor_meta["save_dir"]) / f"iteration-{iteration}")
            if original["task_id"] == GENERATE_TASK_ID and identifier is not None:
                actor_meta["save_dir"] = sql_save_dir + f"{identifier}/task_{iteration}"
            if original["task_id"] == process_ids[-1] and save_path is not None:
                task["dataset_save_path"] = save_path
            cloned_tasks.append(task)

        for original in cpx_task_meta:
            task = copy.deepcopy(original)
            task["task_id"] = f"{original['task_id']}{suffix}"
            task["task_lis"] = _suffix_task_refs(original["task_lis"], suffix)
            if original.get("dataset_save_path"):
                p = Path(task["dataset_save_path"])
                task["dataset_save_path"] = str(p.with_name(f"{p.stem}{suffix}{p.suffix}"))
            if original["task_id"] == process_ids[-1] and save_path is not None:
                task["dataset_save_path"] = save_path
            cloned_complex_tasks.append(task)

        cloned_process.extend(f"{task_id}{suffix}" for task_id in process_ids)
        if save_path is not None:
            save_paths.append(save_path)

    if should_use_process_parallel(iterations):
        cloned_process.append("~p")

    return cloned_tasks, cloned_complex_tasks, cloned_process, save_paths


def init_task_meta(meta_task, n, dataset_save_dir, sql_save_dir, identifier):
    task_id = meta_task['task_id']
    task_lis = []
    save_lis = []
    for ind in range(n):
        new_task = copy.deepcopy(meta_task)
        new_task['task_id'] = task_id + str((ind + 1))
        if identifier is not None:
            save_path = dataset_save_dir + f"{identifier}/task_{ind + 1}.json"
            new_task['dataset_save_path'] = save_path
            new_task["meta"]["actor"]["save_dir"] = sql_save_dir + f"{identifier}/task_{ind + 1}"
            save_lis.append(save_path)
        task_lis.append(new_task)

    return task_lis, save_lis


def _calculate_final_score(
        dataset,
        data_lists,
        eval_type: str = "execute_accuracy",
        quiet: bool = False,
) -> dict:
    """
    Calculate final score across all iterations.

    Args:
        dataset: Base dataset object
        data_lists: List of datasets from different iterations
        eval_type: Type of evaluation to perform

    Returns:
        {"metric": "EX", "eval_type": str, "avg": float, "valid": int, "total": int}
    """
    valid_count = 0
    pass_count = 0
    total = len(data_lists[0]) if data_lists else 0

    for row in zip(*data_lists):
        data_row = list(row)
        sub_dataset = copy.deepcopy(dataset)
        sub_dataset._dataset = data_row

        evaluator = Evaluator(dataset=sub_dataset, eval_type=eval_type)
        results = evaluator.eval_all(verbose=False)

        for key, value in results.items():
            if value.get("valid_num", 0) > 0:
                valid_count += 1
            if value.get("avg", 0) != 0:
                pass_count += 1

    final_score = pass_count / valid_count if valid_count > 0 else 0.0
    result = {
        "metric": "EX",
        "eval_type": eval_type,
        "avg": final_score,
        "pass_count": pass_count,
        "valid": valid_count,
        "total": total,
    }
    if not quiet:
        print(f"Completed {eval_type}: {valid_count}/{total} valid results")
        print(f"Average for {eval_type}: {final_score:.4f}")

    return result


def _load_dataset_from_engine(config_path: str = None, config: dict = None):
    """
    Load dataset from engine's generate task.

    Args:
        config_path: Path to the configuration file
        config: In-memory reproduce config (mutually exclusive with config_path)

    Returns:
        Dataset object or None if not found
    """
    if config is not None:
        router = Router()
        router.init_config(copy.deepcopy(config))
    else:
        router = Router(config_path=config_path)
    engine = Engine(router)

    # Try exact-match "generate" task first; fall back to any task with a dataset
    for key, task in engine.tasks.items():
        if hasattr(task, 'dataset') and task.dataset is not None:
            return task.dataset
        if key == GENERATE_TASK_ID:
            return task.dataset

    return None


def _load_saved_data_lists(save_lis):
    data_lists = []
    for path in save_lis:
        data = load_dataset(resolve_saved_dataset_path(path))
        if isinstance(data, list):
            data_lists.append(data)
        else:
            logger.warning(f"Skip missing or invalid saved dataset: {path}")
    return data_lists


def evaluate(save_lis, config_path: str = None, quiet: bool = False, config: dict = None):
    data_lists = _load_saved_data_lists(save_lis)
    if not data_lists:
        return {
            "metric": "EX",
            "eval_type": "execute_accuracy",
            "avg": 0.0,
            "pass_count": 0,
            "valid": 0,
            "total": 0,
        }
    dataset = _load_dataset_from_engine(config_path=config_path, config=config)
    return _calculate_final_score(dataset, data_lists, quiet=quiet)


def evaluate_with_details(save_lis, config_path: str = None, quiet: bool = False, config: dict = None):
    data_lists = _load_saved_data_lists(save_lis)
    if not data_lists:
        return {
            "metric": "EX",
            "eval_type": "execute_accuracy",
            "avg": 0.0,
            "pass_count": 0,
            "valid": 0,
            "total": 0,
            "per_sample": [],
        }
    dataset = _load_dataset_from_engine(config_path=config_path, config=config)
    result = _calculate_final_score(dataset, data_lists, quiet=quiet)
    per_sample = _calculate_ex_details(dataset, data_lists)
    result["per_sample"] = per_sample
    # 以 per_sample（真正的 pass@k）为唯一真值重算聚合，确保顶层 avg 与逐样本一致
    valid = sum(1 for d in per_sample if d.get("ex") is not None)
    pass_count = sum(1 for d in per_sample if d.get("ex") == 1)
    result["valid"] = valid
    result["pass_count"] = pass_count
    result["total"] = len(per_sample)
    result["avg"] = pass_count / valid if valid > 0 else 0.0
    return result


def _calculate_ex_details(dataset, data_lists) -> list:
    if not data_lists:
        return []
    total = len(data_lists[0])
    details = []
    for i, row_tuple in enumerate(zip(*data_lists)):
        rows = list(row_tuple)
        first = rows[0] if rows else {}
        instance_id = first.get("instance_id", i) if isinstance(first, dict) else i
        try:
            candidate_details = [
                evaluate_execution_detail(row, dataset=dataset, index=i)
                for row in rows
                if isinstance(row, dict)
            ]
            valid = [detail for detail in candidate_details if detail.get("ex") is not None]
            if any(detail.get("ex") == 1 for detail in valid):
                score = 1
            elif valid:
                score = 0
            else:
                score = None
            exec_error = next(
                (
                    detail.get("exec_error")
                    for detail in candidate_details
                    if detail.get("exec_error")
                ),
                None,
            )
            details.append({"index": i, "instance_id": str(instance_id), "ex": score, "exec_error": exec_error})
        except Exception as exc:
            details.append({"index": i, "instance_id": str(instance_id), "ex": None, "exec_error": str(exc)})
    if len(details) < total:
        for i in range(len(details), total):
            first = data_lists[0][i]
            instance_id = first.get("instance_id", i) if isinstance(first, dict) else i
            details.append({
                "index": i,
                "instance_id": str(instance_id),
                "ex": None,
                "exec_error": "missing aligned rows across generate runs",
            })
    return details


def evaluate_custom(
        save_lis: list,
        config_path: str = None,
        eval_fn=None,
        quiet: bool = False,
        config: dict = None,
        **kwargs
    ) -> dict:
    """用自定义评估函数评估多轮结果。

    Parameters
    ----------
    save_lis : list[str]
        n 个数据集保存路径
    config_path : str
        reproduce config 路径
    eval_fn : callable
        签名: eval_fn(rows: list[dict], dataset, row_index: int, **kwargs) -> float | dict | None
        - rows: 同一 question 的 generate_num 轮结果 list
        - dataset: 原始 Dataset 对象（提供 db_path / credential / schema）
        - row_index: 样本索引
        - 返回 None 表示该样本无效

    Returns
    -------
    {"avg": float | None, "scores": list, "valid": int, "total": int}
    """
    data_lists = _load_saved_data_lists(save_lis)
    dataset = _load_dataset_from_engine(config_path=config_path, config=config)

    if not data_lists or not data_lists[0]:
        if not quiet:
            print("[evaluate_custom] No data found.")
        return {"avg": None, "scores": [], "valid": 0, "total": 0, "errors": []}

    total = len(data_lists[0])
    scores = []
    valid = 0
    errors = []

    for i, row_tuple in enumerate(zip(*data_lists)):
        rows = list(row_tuple)
        try:
            score = eval_fn(rows, dataset=dataset, row_index=i, **kwargs)
            if score is not None:
                scores.append(score)
                valid += 1
        except Exception as e:
            errors.append(f"sample {i}: {e}")
            if not quiet:
                print(f"[evaluate_custom] Sample {i} error: {e}")

    if scores and isinstance(scores[0], (int, float)):
        avg = sum(scores) / len(scores)
    else:
        avg = None

    if not quiet:
        if avg is not None:
            print(f"Completed: {valid}/{total} valid results, average = {avg:.4f}")
        elif valid:
            print(f"Completed: {valid}/{total} valid results (structured output, no avg)")
        else:
            print(f"Completed: 0/{total} valid results")

    return {"avg": avg, "scores": scores, "valid": valid, "total": total, "errors": errors}


def evaluate_custom_with_details(
        save_lis: list,
        config_path: str = None,
        eval_fn=None,
        quiet: bool = False,
        config: dict = None,
        **kwargs
    ) -> dict:
    data_lists = _load_saved_data_lists(save_lis)
    dataset = _load_dataset_from_engine(config_path=config_path, config=config)

    if not data_lists or not data_lists[0]:
        if not quiet:
            print("[evaluate_custom] No data found.")
        return {"avg": None, "scores": [], "valid": 0, "total": 0, "errors": [], "per_sample": []}

    total = len(data_lists[0])
    scores = []
    valid = 0
    errors = []
    per_sample = []

    for i, row_tuple in enumerate(zip(*data_lists)):
        rows = list(row_tuple)
        first = rows[0] if rows else {}
        instance_id = first.get("instance_id", i) if isinstance(first, dict) else i
        try:
            score = eval_fn(rows, dataset=dataset, row_index=i, **kwargs)
            detail = {"index": i, "instance_id": str(instance_id), "score": score}
            if score is not None:
                scores.append(score)
                valid += 1
            per_sample.append(detail)
        except Exception as e:
            message = f"sample {i}: {e}"
            errors.append(message)
            per_sample.append({"index": i, "instance_id": str(instance_id), "score": None, "error": str(e)})
            if not quiet:
                print(f"[evaluate_custom] Sample {i} error: {e}")

    if len(per_sample) < total:
        for i in range(len(per_sample), total):
            first = data_lists[0][i]
            instance_id = first.get("instance_id", i) if isinstance(first, dict) else i
            message = "missing aligned rows across generate runs"
            errors.append(f"sample {i}: {message}")
            per_sample.append({"index": i, "instance_id": str(instance_id), "score": None, "error": message})

    if scores and isinstance(scores[0], (int, float)):
        avg = sum(scores) / len(scores)
    else:
        avg = None

    if not quiet:
        if avg is not None:
            print(f"Completed: {valid}/{total} valid results, average = {avg:.4f}")
        elif valid:
            print(f"Completed: {valid}/{total} valid results (structured output, no avg)")
        else:
            print(f"Completed: 0/{total} valid results")

    return {
        "avg": avg,
        "scores": scores,
        "valid": valid,
        "total": total,
        "errors": errors,
        "per_sample": per_sample,
    }
