import copy
import json
import os
import threading

try:
    from . import tools
except ImportError:
    import tools


ADMIN_AUDIT_LOCK = threading.Lock()


def append_admin_audit(record: dict, filename: str) -> str:
    audit_dir = os.path.join(tools.get_service_log_root(), "admin")
    audit_path = os.path.join(audit_dir, filename)
    os.makedirs(audit_dir, exist_ok=True)
    with ADMIN_AUDIT_LOCK:
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return audit_path


def append_admin_cleanup_audit(record: dict) -> str:
    return append_admin_audit(record, "cleanup_audit.jsonl")


def sync_service_instance_status_file(meta: dict) -> None:
    status_file = str(meta.get("status_file") or "")
    if not status_file or not os.path.exists(status_file):
        return
    payload = tools.load_json_file(status_file, {})
    if not isinstance(payload, dict):
        payload = {}
    payload["status"] = str(meta.get("status") or "")
    payload["finished_at"] = meta.get("finished_at")
    payload["admin_cleanup_at"] = meta.get("admin_cleanup_at")
    tools.atomic_write_json(status_file, payload)


def _admin_cleanup_local_resources(execute: bool) -> dict:
    """Reconcile stale local resources without touching healthy running work."""
    service_result = {"scanned": 0, "fixed": 0, "cleaned": 0, "items": []}
    for instance_id in tools.list_service_instance_ids():
        original = tools.load_service_instance(instance_id)
        if not original:
            continue
        service_result["scanned"] += 1
        previous_status = str(original.get("status") or "")
        meta = tools.refresh_service_instance_status(copy.deepcopy(original))
        refreshed_status = str(meta.get("status") or "")
        port_ownership = tools.service_instance_port_ownership(meta)
        process_ownership = tools.service_instance_process_ownership(
            meta, port_ownership
        )
        verified_pids = process_ownership["owned"]
        reused_pids = process_ownership["reused"]
        unverifiable_pids = process_ownership["unverified"]
        eligible = refreshed_status in {"degraded", "failed", "stopped"}
        item = {
            "instance_id": instance_id,
            "previous_status": previous_status,
            "refreshed_status": refreshed_status,
            "eligible": eligible,
            "verified_pids": verified_pids,
            "reused_pids": reused_pids,
            "unverifiable_pids": unverifiable_pids,
            "owned_ports": port_ownership["owned"],
            "reused_ports": port_ownership["reused"],
            "unverified_ports": port_ownership["unverified"],
            "closed_ports": port_ownership["closed"],
        }
        status_changed = refreshed_status != previous_status
        if eligible and verified_pids:
            item["action"] = "cleanup" if execute else "would_cleanup"
            if execute:
                item["process_result"] = tools.terminate_instance_owned_processes(
                    meta
                )
                remaining_ports = tools.service_instance_port_ownership(meta)
                remaining_processes = tools.service_instance_process_ownership(
                    meta, remaining_ports
                )
                remaining_verified = remaining_processes["owned"]
                remaining_unverifiable = remaining_processes["unverified"]
                item["remaining_verified_pids"] = remaining_verified
                item["unverifiable_pids"] = remaining_unverifiable
                item["owned_ports"] = remaining_ports["owned"]
                item["reused_ports"] = remaining_ports["reused"]
                item["unverified_ports"] = remaining_ports["unverified"]
                item["closed_ports"] = remaining_ports["closed"]
                if (
                    not remaining_verified
                    and not remaining_unverifiable
                    and not item["owned_ports"]
                    and not item["unverified_ports"]
                ):
                    meta["status"] = "stopped"
                    tools.finish_meta_if_missing(meta)
                else:
                    meta["status"] = "degraded"
                meta["admin_cleanup_at"] = tools.current_time_text()
                service_result["cleaned"] += 1
        elif (
            refreshed_status == "degraded"
            and not unverifiable_pids
            and not item["owned_ports"]
            and not item["unverified_ports"]
        ):
            item["action"] = (
                "finalize_stopped" if execute else "would_finalize_stopped"
            )
            if execute:
                meta["status"] = "stopped"
                tools.finish_meta_if_missing(meta)
                meta["admin_cleanup_at"] = tools.current_time_text()
                service_result["cleaned"] += 1
        elif eligible and (unverifiable_pids or item["unverified_ports"]):
            item["action"] = "blocked_unverified"
        elif status_changed:
            item["action"] = "fix_status" if execute else "would_fix_status"
        else:
            item["action"] = "none"

        if status_changed:
            service_result["fixed"] += 1
        if execute and (
            status_changed or item["action"] in {"cleanup", "finalize_stopped"}
        ):
            tools.save_service_instance(meta)
            sync_service_instance_status_file(meta)
        if item["action"] != "none" or eligible:
            item["final_status"] = str(meta.get("status") or "")
            service_result["items"].append(item)

    benchmark_result = {"scanned": 0, "fixed": 0, "items": []}
    for job_id, meta_path, original in tools.iter_json_records(
        tools.get_benchmark_log_dir(), "meta.json"
    ):
        benchmark_result["scanned"] += 1
        previous_status = str(original.get("status") or "")
        meta = tools.refresh_benchmark_job_meta(
            job_id, meta_path, copy.deepcopy(original), persist=execute
        )
        current_status = str(meta.get("status") or "")
        if current_status != previous_status:
            benchmark_result["fixed"] += 1
            benchmark_result["items"].append(
                {
                    "job_id": job_id,
                    "previous_status": previous_status,
                    "current_status": current_status,
                }
            )

    test_result = {"scanned": 0, "fixed": 0, "items": []}
    test_root = os.path.join(tools.get_test_log_root(), "runs")
    for test_run_id, status_file, original in tools.iter_json_records(
        test_root, "status.json"
    ):
        test_result["scanned"] += 1
        previous_status = str(original.get("status") or "")
        meta = tools.refresh_test_run_meta(
            test_run_id, status_file, copy.deepcopy(original), persist=execute
        )
        current_status = str(meta.get("status") or "")
        if current_status != previous_status:
            test_result["fixed"] += 1
            test_result["items"].append(
                {
                    "test_run_id": test_run_id,
                    "previous_status": previous_status,
                    "current_status": current_status,
                }
            )

    change_actions = {
        "cleanup",
        "would_cleanup",
        "finalize_stopped",
        "would_finalize_stopped",
        "fix_status",
        "would_fix_status",
    }
    service_changes = sum(
        item.get("action") in change_actions for item in service_result["items"]
    )
    result = {
        "status": "ok",
        "operation": "apply" if execute else "preview",
        "current_time": tools.current_time_text(),
        "summary": {
            "services": service_changes,
            "benchmarks": benchmark_result["fixed"],
            "tests": test_result["fixed"],
            "total": (
                service_changes
                + benchmark_result["fixed"]
                + test_result["fixed"]
            ),
        },
        "services": service_result,
        "benchmarks": benchmark_result,
        "tests": test_result,
    }
    if execute:
        result["audit_file"] = append_admin_cleanup_audit(result)
    return result


def admin_preview_cleanup() -> dict:
    """Preview local stale-resource cleanup without persisting changes."""
    return _admin_cleanup_local_resources(execute=False)


def admin_apply_cleanup() -> dict:
    """Re-scan and apply local stale-resource cleanup with audit logging."""
    return _admin_cleanup_local_resources(execute=True)


def admin_list_service_instances(limit: int = 20, status: str = "") -> dict:
    """List local service instances without applying user visibility filters."""
    limit = tools.clamp_int(limit, 20, 1, tools.MAX_LIST_LIMIT)
    status_filter = str(status or "").strip().lower()
    items = []
    for instance_id in tools.list_service_instance_ids():
        meta = tools.visible_service_instance_meta(instance_id)
        if not meta:
            continue
        current_status = str(meta.get("status") or "unknown").lower()
        if status_filter and current_status != status_filter:
            continue
        items.append((instance_id, meta))

    items.sort(
        key=lambda item: (
            tools.status_sort_rank(item[1].get("status")),
            -tools.parse_time_sort_value(item[1].get("started_at")),
            item[0],
        )
    )
    total = len(items)
    visible_items = items[:limit]
    records = []
    for instance_id, meta in visible_items:
        tasks = tools.running_tasks_for_service_instance(instance_id)
        benchmark_tasks = tasks.get("benchmark") or []
        test_tasks = tasks.get("tests") or []
        records.append(
            {
                "instance_id": instance_id,
                "status": str(meta.get("status") or "unknown"),
                "owner_user_id": str(meta.get("owner_user_id") or ""),
                "model": str(meta.get("model") or ""),
                "gpus": str(meta.get("actual_gpus") or ""),
                "ports": dict(meta.get("ports") or {}),
                "started_at": meta.get("started_at"),
                "finished_at": meta.get("finished_at"),
                "runtime_active": tools.service_instance_runtime_active(meta),
                "running_tasks": {
                    "benchmark": len(benchmark_tasks),
                    "tests": len(test_tasks),
                },
            }
        )

    return {
        "status": "ok",
        "current_time": tools.current_time_text(),
        "filter": {"status": status_filter or None, "limit": limit},
        "total": total,
        "returned": len(records),
        "instances": records,
    }


def admin_list_benchmark_jobs(
    limit: int = 20, status: str = "", instance_id: str = ""
) -> dict:
    """List local benchmark jobs without applying user visibility filters."""
    limit = tools.clamp_int(limit, 20, 1, tools.MAX_LIST_LIMIT)
    status_filter = str(status or "").strip().lower()
    instance_filter = str(instance_id or "").strip()
    jobs = []
    for job_id, meta_path, original in tools.iter_json_records(
        tools.get_benchmark_log_dir(), "meta.json"
    ):
        meta = tools.refresh_benchmark_job_meta(job_id, meta_path, original)
        current_status = str(meta.get("status") or "unknown").lower()
        if status_filter and current_status != status_filter:
            continue
        if (
            instance_filter
            and str(meta.get("service_instance_id") or "") != instance_filter
        ):
            continue
        sort_time = tools.parse_time_sort_value(meta.get("start_time"))
        if not sort_time:
            sort_time = tools.parse_time_sort_value(meta.get("job_id", job_id))
        if not sort_time:
            sort_time = os.path.getmtime(meta_path)
        jobs.append((job_id, sort_time, meta))

    jobs.sort(
        key=lambda item: (
            tools.status_sort_rank(item[2].get("status")),
            -item[1],
            item[0],
        )
    )
    total = len(jobs)
    records = []
    for job_id, _, meta in jobs[:limit]:
        pid = int(meta.get("pid") or 0)
        records.append(
            {
                "job_id": job_id,
                "status": str(meta.get("status") or "unknown"),
                "owner_user_id": tools.task_owner_user_id(meta),
                "service_instance_id": str(meta.get("service_instance_id") or ""),
                "dataset": str(meta.get("dataset") or ""),
                "benchmark_type": str(
                    meta.get("benchmark_type") or meta.get("mode") or ""
                ),
                "model": str(meta.get("model") or ""),
                "pid": pid,
                "process_running": tools.pid_is_alive(pid) if pid else False,
                "start_time": meta.get("start_time"),
                "end_time": meta.get("end_time"),
                "log": tools.format_agent_relative_path(meta.get("log", "")),
                "output": tools.format_agent_relative_path(meta.get("output", "")),
            }
        )

    return {
        "status": "ok",
        "current_time": tools.current_time_text(),
        "filter": {
            "status": status_filter or None,
            "instance_id": instance_filter or None,
            "limit": limit,
        },
        "total": total,
        "returned": len(records),
        "benchmarks": records,
    }


def _admin_stop_benchmark_job(job_id: str, execute: bool) -> dict:
    """Stop one explicitly selected benchmark without owner restrictions."""
    operation = "apply" if execute else "preview"
    job_id = str(job_id or "").strip()
    if not job_id or "/" in job_id or ".." in job_id:
        return {
            "status": "error",
            "operation": operation,
            "job_id": job_id,
            "message": "Invalid job_id",
        }

    meta_file = os.path.join(tools.get_benchmark_log_dir(), job_id, "meta.json")
    if not os.path.exists(meta_file):
        return {
            "status": "not_found",
            "operation": operation,
            "job_id": job_id,
            "message": f"Benchmark任务不存在: {job_id}",
        }
    meta = tools.load_json_file(meta_file, {})
    meta = tools.refresh_benchmark_job_meta(
        job_id, meta_file, meta, persist=execute
    )
    current_status = str(meta.get("status") or "unknown")
    response = {
        "status": "ok",
        "operation": operation,
        "can_apply": current_status == "running",
        "job_id": job_id,
        "job_status": current_status,
        "owner_user_id": tools.task_owner_user_id(meta),
        "service_instance_id": str(meta.get("service_instance_id") or ""),
        "dataset": str(meta.get("dataset") or ""),
        "pid": int(meta.get("pid") or 0),
        "output": tools.format_agent_relative_path(meta.get("output", "")),
    }
    if current_status != "running":
        response["can_apply"] = False
        response["message"] = "Benchmark任务当前未运行，无需停止。"
        return response
    if not execute:
        response["message"] = (
            "该操作将停止正在运行的 Benchmark；如需执行，请调用 stop/apply 接口。"
        )
        return response

    stop_result = tools.stop_benchmark_job_runtime(job_id, meta_file, meta)
    final_meta = tools.load_json_file(meta_file, {})
    final_meta = tools.refresh_benchmark_job_meta(job_id, meta_file, final_meta)
    final_status = str(final_meta.get("status") or "unknown")
    pid = int(final_meta.get("pid") or 0)
    process_running = tools.pid_is_alive(pid) if pid else False
    stopped = final_status != "running" and not process_running
    audit_record = {
        "action": "admin_benchmark_stop",
        "time": tools.current_time_text(),
        "job_id": job_id,
        "owner_user_id": tools.task_owner_user_id(meta),
        "service_instance_id": str(meta.get("service_instance_id") or ""),
        "previous_status": current_status,
        "final_status": final_status,
        "success": stopped,
        "result": stop_result,
    }
    audit_file = append_admin_audit(audit_record, "benchmark_stop_audit.jsonl")
    return {
        "status": "ok" if stopped else "error",
        "operation": "apply",
        "job_id": job_id,
        "previous_status": current_status,
        "job_status": final_status,
        "process_running": process_running,
        "result": stop_result,
        "audit_file": audit_file,
    }


def admin_preview_benchmark_stop(job_id: str) -> dict:
    """Preview stopping one benchmark without changing its state."""
    return _admin_stop_benchmark_job(job_id, execute=False)


def admin_apply_benchmark_stop(job_id: str) -> dict:
    """Re-check and stop one benchmark with audit logging."""
    return _admin_stop_benchmark_job(job_id, execute=True)


def admin_list_test_runs(
    limit: int = 20, status: str = "", instance_id: str = ""
) -> dict:
    """List local service-test runs without applying user visibility filters."""
    limit = tools.clamp_int(limit, 20, 1, tools.MAX_LIST_LIMIT)
    status_filter = str(status or "").strip().lower()
    instance_filter = str(instance_id or "").strip()
    runs_dir = os.path.join(tools.get_test_log_root(), "runs")
    runs = []
    for test_run_id, status_file, original in tools.iter_json_records(
        runs_dir, "status.json"
    ):
        if not original:
            if status_filter and status_filter != "corrupt":
                continue
            if instance_filter:
                continue
            runs.append(
                (
                    test_run_id,
                    tools.parse_time_sort_value(test_run_id),
                    {
                        "test_run_id": test_run_id,
                        "status": "corrupt",
                        "state_error": "status.json is empty or invalid",
                    },
                )
            )
            continue
        meta = tools.refresh_test_run_meta(test_run_id, status_file, original)
        current_status = str(meta.get("status") or "unknown").lower()
        if status_filter and current_status != status_filter:
            continue
        if (
            instance_filter
            and str(meta.get("service_instance_id") or "") != instance_filter
        ):
            continue
        sort_time = tools.parse_time_sort_value(meta.get("started_at"))
        if not sort_time:
            sort_time = tools.parse_time_sort_value(test_run_id)
        if not sort_time:
            sort_time = os.path.getmtime(status_file)
        runs.append((test_run_id, sort_time, meta))

    runs.sort(
        key=lambda item: (
            tools.status_sort_rank(item[2].get("status")),
            -item[1],
            item[0],
        )
    )
    total = len(runs)
    records = []
    for test_run_id, _, meta in runs[:limit]:
        tests = meta.get("tests") or {}
        status_counts = {}
        for item in tests.values():
            item_status = str(item.get("status") or "unknown")
            status_counts[item_status] = status_counts.get(item_status, 0) + 1
        script_pid = int(meta.get("script_pid") or 0)
        records.append(
            {
                "test_run_id": test_run_id,
                "status": str(meta.get("status") or "unknown"),
                "owner_user_id": tools.task_owner_user_id(meta),
                "service_instance_id": str(meta.get("service_instance_id") or ""),
                "test_name": str(meta.get("test_name") or ""),
                "script_pid": script_pid,
                "process_running": tools.test_run_is_active(meta),
                "started_at": meta.get("started_at"),
                "finished_at": meta.get("finished_at"),
                "log_file": tools.format_test_path(meta.get("log_file", "")),
                "state_error": meta.get("state_error"),
                "scripts": {
                    "total": len(tests),
                    "status_counts": status_counts,
                },
            }
        )

    return {
        "status": "ok",
        "current_time": tools.current_time_text(),
        "filter": {
            "status": status_filter or None,
            "instance_id": instance_filter or None,
            "limit": limit,
        },
        "total": total,
        "returned": len(records),
        "tests": records,
    }


def _admin_stop_test_run(test_run_id: str, execute: bool) -> dict:
    """Stop one explicitly selected service-test run without owner restrictions."""
    operation = "apply" if execute else "preview"
    test_run_id = str(test_run_id or "").strip()
    if not test_run_id or "/" in test_run_id or ".." in test_run_id:
        return {
            "status": "error",
            "operation": operation,
            "test_run_id": test_run_id,
            "message": "Invalid test_run_id",
        }

    status_file = tools.get_test_status_path(test_run_id)
    if not os.path.exists(status_file):
        return {
            "status": "not_found",
            "operation": operation,
            "test_run_id": test_run_id,
            "message": f"功能测试任务不存在: {test_run_id}",
        }
    meta = tools.load_json_file(status_file, {})
    if not meta:
        return {
            "status": "error",
            "operation": operation,
            "test_run_id": test_run_id,
            "message": "功能测试状态文件为空或无法解析，不能安全执行停止操作。",
        }
    meta = tools.refresh_test_run_meta(
        test_run_id, status_file, meta, persist=execute
    )
    current_status = str(meta.get("status") or "unknown")
    response = {
        "status": "ok",
        "operation": operation,
        "can_apply": current_status == "running",
        "test_run_id": test_run_id,
        "test_status": current_status,
        "owner_user_id": tools.task_owner_user_id(meta),
        "service_instance_id": str(meta.get("service_instance_id") or ""),
        "test_name": str(meta.get("test_name") or ""),
        "log_file": tools.format_test_path(meta.get("log_file", "")),
    }
    if current_status != "running":
        response["can_apply"] = False
        response["message"] = "功能测试任务当前未运行，无需停止。"
        return response
    if not execute:
        response["message"] = (
            "该操作将停止正在运行的功能测试；如需执行，请调用 stop/apply 接口。"
        )
        return response

    stop_result = tools.stop_test_run_runtime(test_run_id, status_file, meta)
    final_meta = tools.load_json_file(status_file, {})
    final_meta = tools.refresh_test_run_meta(test_run_id, status_file, final_meta)
    final_status = str(final_meta.get("status") or "unknown")
    process_running = tools.test_run_is_active(final_meta)
    stopped = final_status != "running" and not process_running
    audit_record = {
        "action": "admin_test_stop",
        "time": tools.current_time_text(),
        "test_run_id": test_run_id,
        "owner_user_id": tools.task_owner_user_id(meta),
        "service_instance_id": str(meta.get("service_instance_id") or ""),
        "previous_status": current_status,
        "final_status": final_status,
        "success": stopped,
        "result": stop_result,
    }
    audit_file = append_admin_audit(audit_record, "test_stop_audit.jsonl")
    return {
        "status": "ok" if stopped else "error",
        "operation": "apply",
        "test_run_id": test_run_id,
        "previous_status": current_status,
        "test_status": final_status,
        "process_running": process_running,
        "result": stop_result,
        "audit_file": audit_file,
    }


def admin_preview_test_stop(test_run_id: str) -> dict:
    """Preview stopping one service-test run without changing its state."""
    return _admin_stop_test_run(test_run_id, execute=False)


def admin_apply_test_stop(test_run_id: str) -> dict:
    """Re-check and stop one service-test run with audit logging."""
    return _admin_stop_test_run(test_run_id, execute=True)


def _admin_stop_service_instance(instance_id: str, execute: bool) -> dict:
    """Stop one explicitly selected instance without applying owner restrictions."""
    operation = "apply" if execute else "preview"
    instance_id = str(instance_id or "").strip()
    if not instance_id or "/" in instance_id or ".." in instance_id:
        return {
            "status": "error",
            "operation": operation,
            "instance_id": instance_id,
            "message": "Invalid instance_id",
        }

    meta = tools.refresh_service_instance_status(
        copy.deepcopy(tools.load_service_instance(instance_id))
    )
    if not meta:
        return {
            "status": "not_found",
            "operation": operation,
            "instance_id": instance_id,
            "message": f"推理服务实例不存在: {instance_id}",
        }

    tasks = tools.running_tasks_for_service_instance(instance_id)
    runtime_active = tools.service_instance_runtime_active(meta)
    response = {
        "status": "ok",
        "operation": operation,
        "can_apply": runtime_active,
        "instance_id": instance_id,
        "owner_user_id": str(meta.get("owner_user_id") or ""),
        "instance_status": str(meta.get("status") or ""),
        "gpus": str(meta.get("actual_gpus") or ""),
        "ports": dict(meta.get("ports") or {}),
        "running_tasks": tasks,
    }
    if tasks.get("benchmark") or tasks.get("tests"):
        response["status"] = "blocked"
        response["can_apply"] = False
        response["message"] = (
            "该实例仍有关联的 benchmark 或功能测试正在运行，请先停止关联任务。"
        )
        return response

    if not runtime_active:
        if execute and str(meta.get("status") or "") != "stopped":
            meta["status"] = "stopped"
            tools.finish_meta_if_missing(meta)
            tools.save_service_instance(meta)
            sync_service_instance_status_file(meta)
        response["status"] = "ok"
        response["can_apply"] = False
        response["instance_status"] = "stopped"
        response["message"] = "实例已停止，无需重复操作。"
        return response

    if not execute:
        response["message"] = (
            "该操作将强制停止正常运行的推理服务实例；"
            "如需执行，请调用 stop/apply 接口。"
        )
        return response

    previous_status = str(meta.get("status") or "")
    stop_result = tools.stop_service_instance_runtime(meta)
    final_meta = tools.visible_service_instance_meta(instance_id)
    stopped = bool(final_meta) and not tools.service_instance_runtime_active(final_meta)
    if stopped:
        final_meta["status"] = "stopped"
        tools.finish_meta_if_missing(final_meta)
        final_meta["admin_stopped_at"] = tools.current_time_text()
        tools.save_service_instance(final_meta)
        sync_service_instance_status_file(final_meta)

    audit_record = {
        "action": "admin_service_stop",
        "time": tools.current_time_text(),
        "instance_id": instance_id,
        "owner_user_id": str(meta.get("owner_user_id") or ""),
        "previous_status": previous_status,
        "final_status": str(final_meta.get("status") or "") if final_meta else "",
        "success": stopped,
        "result": stop_result,
    }
    audit_file = append_admin_audit(audit_record, "service_stop_audit.jsonl")
    return {
        "status": "ok" if stopped else "error",
        "operation": "apply",
        "instance_id": instance_id,
        "previous_status": previous_status,
        "instance_status": audit_record["final_status"],
        "result": stop_result,
        "audit_file": audit_file,
    }


def admin_preview_service_stop(instance_id: str) -> dict:
    """Preview stopping one service instance without changing its state."""
    return _admin_stop_service_instance(instance_id, execute=False)


def admin_apply_service_stop(instance_id: str) -> dict:
    """Re-check and stop one service instance with audit logging."""
    return _admin_stop_service_instance(instance_id, execute=True)
