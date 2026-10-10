from celery.schedules import crontab
from redbeat import RedBeatSchedulerEntry
from app.core.celery_app import celery_app


TASK = "app.tasks.schedule.scheduled_regression"


def _entry_name(schedule_id):
    return f"schedule-{schedule_id}"


def _parse_cron(cron):
    minute, hour, dom, month, dow = cron.split()
    return crontab(minute=minute, hour=hour, day_of_month=dom,
                   month_of_year=month, day_of_week=dow)


def sync_schedule(schedule):
    if not schedule.enabled:
        remove_schedule(schedule.id)
        return
    if getattr(schedule, "env_id", None) is None:
        remove_schedule(schedule.id)
        raise ValueError("定时任务必须先选择执行环境")
    entry = RedBeatSchedulerEntry(
        _entry_name(schedule.id),
        TASK,
        _parse_cron(schedule.cron),
        args=[schedule.project_id, schedule.tag, schedule.suite_id, schedule.env_id],
        app=celery_app,
    )
    entry.save()


def schedule_is_synced(schedule):
    """Check desired definition AND sorted-set membership, without resetting due time."""
    key = "redbeat:" + _entry_name(schedule.id)
    try:
        entry = RedBeatSchedulerEntry.from_key(key, app=celery_app)
    except KeyError:
        return not schedule.enabled
    if not schedule.enabled or getattr(schedule, "env_id", None) is None:
        return False
    from redbeat.schedulers import get_redis
    client = get_redis(celery_app)
    return (
        entry.task == TASK
        and list(entry.args) == [schedule.project_id, schedule.tag, schedule.suite_id, schedule.env_id]
        and entry.schedule == _parse_cron(schedule.cron)
        and client.zscore(entry.app.redbeat_conf.schedule_key, entry.key) is not None
    )


def remove_schedule(schedule_id):
    key = "redbeat:" + _entry_name(schedule_id)
    try:
        RedBeatSchedulerEntry.from_key(key, app=celery_app).delete()
    except KeyError:
        pass













