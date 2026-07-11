__all__ = [
    "aggregate_cf1",
    "evaluate",
    "evaluate_custom",
    "evaluate_custom_with_details",
    "evaluate_with_details",
    "expand_execution_graph",
    "load_router",
    "print_eval_report",
    "print_report_header",
    "resolve_saved_dataset_path",
    "should_use_process_parallel",
]


def __getattr__(name):
    if name in {"aggregate_cf1", "print_eval_report", "print_report_header"}:
        from reproduce.eval import report
        return getattr(report, name)
    if name in {
        "evaluate",
        "evaluate_custom",
        "evaluate_custom_with_details",
        "evaluate_with_details",
        "expand_execution_graph",
        "load_router",
        "resolve_saved_dataset_path",
        "should_use_process_parallel",
    }:
        from reproduce.eval import utils
        return getattr(utils, name)
    raise AttributeError(name)
