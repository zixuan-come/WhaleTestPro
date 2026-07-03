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
    entry = RedBeatSchedulerEntry(
        _entry_name(schedule.id),
        TASK,
        _parse_cron(schedule.cron),
        # args 顺序:project_id 在前,tag 在后 —— task 侧签名要一致
        args=[schedule.project_id, schedule.tag],
        app=celery_app,
    )
    entry.save()


def remove_schedule(schedule_id):
    key = "redbeat:" + _entry_name(schedule_id)
    try:
        RedBeatSchedulerEntry.from_key(key, app=celery_app).delete()
    except KeyError:
        pass













