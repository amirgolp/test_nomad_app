"""Resource usage and content statistics of the NOMAD Oasis.

The Lab Monitor is mounted inside the NOMAD app, so the process measured here
is the one serving NOMAD.
"""

import os
import time

import psutil
from nomad.config import config

# psutil measures CPU usage between two calls on the same Process object, so
# the objects are kept between samples.
_processes: dict[int, psutil.Process] = {}


def _nomad_root_process() -> psutil.Process:
    current = psutil.Process(os.getpid())
    parent = current.parent()
    # With several gunicorn workers, report the master and all of its workers.
    try:
        if parent is not None and 'gunicorn' in ' '.join(parent.cmdline()):
            return parent
    except psutil.Error:
        pass
    return current


def _tracked(process: psutil.Process) -> psutil.Process:
    tracked = _processes.get(process.pid)
    if tracked is None or not tracked.is_running():
        tracked = _processes[process.pid] = process
    return tracked


def system_stats() -> dict:
    root = _nomad_root_process()
    try:
        tree = [root, *root.children(recursive=True)]
    except psutil.Error:
        tree = [root]

    cpu_percent, rss_bytes, n_threads, n_processes = 0.0, 0, 0, 0
    for process in map(_tracked, tree):
        try:
            with process.oneshot():
                cpu_percent += process.cpu_percent(interval=None)
                rss_bytes += process.memory_info().rss
                n_threads += process.num_threads()
                n_processes += 1
        except psutil.Error:
            continue

    memory = psutil.virtual_memory()
    disk_path = next(
        (p for p in (config.fs.staging, config.fs.public) if p and os.path.exists(p)),
        '/',
    )
    disk = psutil.disk_usage(disk_path)

    return {
        'timestamp': time.time(),
        'host_cpu_percent': psutil.cpu_percent(interval=None),
        'host_cpu_count': psutil.cpu_count(),
        'host_load_average': os.getloadavg(),
        'host_memory_percent': memory.percent,
        'host_memory_used_bytes': memory.total - memory.available,
        'host_memory_total_bytes': memory.total,
        'disk_path': disk_path,
        'disk_percent': disk.percent,
        'disk_used_bytes': disk.used,
        'disk_total_bytes': disk.total,
        'nomad_cpu_percent': cpu_percent,
        'nomad_rss_bytes': rss_bytes,
        'nomad_threads': n_threads,
        'nomad_processes': n_processes,
        'nomad_uptime_seconds': time.time() - root.create_time(),
    }


def content_stats() -> dict:
    from nomad.processing import ProcessStatus, Upload
    from nomad.search import get_statistics

    return {
        'version': config.meta.version,
        'deployment': config.meta.deployment,
        'public': get_statistics(),
        'uploads_total': Upload.objects.count(),
        'uploads_processing': Upload.objects(
            process_status__in=ProcessStatus.STATUSES_PROCESSING
        ).count(),
    }
