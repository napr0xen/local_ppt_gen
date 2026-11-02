from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4


_jobs = {}
_jobs_lock = Lock()


def create_job(source_filename, template_name, model):
    """Create and store a new presentation-generation job."""

    job_id = str(uuid4())

    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "Waiting to start",
        "progress": 0,
        "source_filename": source_filename,
        "template_name": template_name,
        "model": model,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "result": None,
        "error": None,
    }

    with _jobs_lock:
        _jobs[job_id] = job

    return job.copy()


def update_job(job_id, **changes):
    """Update a job without exposing the internal dictionary."""

    with _jobs_lock:
        job = _jobs.get(job_id)

        if job is None:
            raise KeyError(f"Presentation job not found: {job_id}")

        job.update(changes)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()

        return job.copy()


def get_job(job_id):
    """Return a safe copy of a job."""

    with _jobs_lock:
        job = _jobs.get(job_id)

        if job is None:
            return None

        return job.copy()


def list_jobs():
    """Return all jobs, newest first."""

    with _jobs_lock:
        jobs = [job.copy() for job in _jobs.values()]

    return sorted(
        jobs,
        key=lambda item: item["created_at"],
        reverse=True,
    )