"""Independent executions, destructive-history boundaries and TPS; no external IO."""
import copy
from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.perf import PerfTask, PerfRun
from app.core.perf_history import transaction_sample
from app.core.migrations import ensure_perf_run_schema
from app.repositories import perf as repo
from app.schemas.perf import PerfRunClear
from tests.test_perf_lifecycle import perf_control
from tests.test_project_notifications import notifications


def finish(db, task, key, requests=30):
    repo.db_update_if_status(db, task.id, task.project_id, task.status, status='queued', celery_task_id=key,
                             queued_at=datetime.utcnow())
    return repo.db_update_if_status(db, task.id, task.project_id, 'queued', status='done', rps=10,
        request_stats=[{'name':'step_01','method':'GET','num_requests':requests,'num_failures':0}],
        iteration_stats={'iterations':10,'failures':1,'elapsed_seconds':2,'iteration_rps':5},
        finished_at=datetime.utcnow())


def test_repeat_preserves_previous_snapshot_and_resets_counters(perf_control):
    perf,db,(task,_),cache,_response=perf_control
    finish(db,task,'first')
    first=db.query(PerfRun).one();snapshot=copy.deepcopy(first.snapshot)
    # Changing the reusable definition must not change the first execution.
    repo.db_update(db,task.id,1,users=20)
    assert db.get(PerfRun,first.id).snapshot==snapshot
    queued=perf.s_mark_queued(db,task.id,1,'second')
    assert queued.status=='queued' and queued.rps is None and queued.request_stats is None
    assert queued.iteration_stats is None and queued.finished_at is None
    rows=db.query(PerfRun).order_by(PerfRun.id).all()
    assert len(rows)==2 and rows[0].snapshot==snapshot and rows[1].snapshot['users']==20
    with pytest.raises(perf.PerfRunBusyError):perf.s_mark_queued(db,task.id,1,'third')
    assert db.query(PerfRun).count()==2


def test_cancelled_definition_can_run_again_without_stale_cancel_flag(perf_control):
    perf,db,(task,_),cache,_response=perf_control
    perf.s_mark_queued(db,task.id,1,'first');perf.s_cancel(db,task.id,1)
    cache.set(f'locust:cancel:1:{task.id}','1')
    assert perf.s_mark_queued(db,task.id,1,'second').status=='queued'
    assert cache.get(f'locust:cancel:1:{task.id}') is None
    with pytest.raises(perf.PerfRunBusyError):perf.s_cancel(db,task.id,1,'first')
    assert task.status=='queued'


def test_clear_all_retains_config_and_active_run_selection_is_atomic(perf_control):
    perf,db,(task,_),cache,_response=perf_control
    finish(db,task,'first');first=db.query(PerfRun).one()
    perf.s_mark_queued(db,task.id,1,'second');second=db.query(PerfRun).order_by(PerfRun.id.desc()).first()
    with pytest.raises(ValueError):perf.s_clear_runs(db,task.id,1,PerfRunClear(run_ids=[first.id,second.id]))
    assert db.query(PerfRun).count()==2
    assert perf.s_clear_runs(db,task.id,1,PerfRunClear(all_finished=True))==1
    assert db.query(PerfRun).one().id==second.id and task.status=='queued'
    perf.s_cancel(db,task.id,1)
    assert perf.s_clear_runs(db,task.id,1,PerfRunClear(all_finished=True))==1
    assert task.status=='pending' and task.name=='old' and task.target_path=='/old'
    assert db.query(PerfRun).count()==0
    assert perf.s_mark_queued(db,task.id,1,'third').status=='queued'


def test_selective_clear_restores_latest_remaining_result_and_tenant_scope(perf_control):
    perf,db,(task,_),cache,_response=perf_control
    finish(db,task,'first',30);first=db.query(PerfRun).one()
    finish(db,task,'second',60);second=db.query(PerfRun).order_by(PerfRun.id.desc()).first()
    assert perf.s_clear_runs(db,task.id,999,PerfRunClear(run_ids=[second.id])) is None
    with pytest.raises(LookupError):perf.s_clear_runs(db,task.id,1,PerfRunClear(run_ids=[9999]))
    assert perf.s_clear_runs(db,task.id,1,PerfRunClear(run_ids=[second.id]))==1
    assert task.request_stats[0]['num_requests']==30 and task.celery_task_id=='first'
    assert db.query(PerfRun).one().id==first.id


def test_late_worker_cannot_modify_a_new_execution(perf_control):
    perf,db,(task,_),cache,_response=perf_control
    finish(db,task,'first');perf.s_mark_queued(db,task.id,1,'second')
    repo.db_update_if_status(db,task.id,1,'queued',status='running')
    db.info['perf_execution']=(task.id,1,'first')
    try:
        assert repo.db_update_if_status(db,task.id,1,'running',status='done',rps=999) is None
        assert repo.db_update_if_status_in(db,task.id,1,('queued','running'),status='failed') is None
    finally:db.info.pop('perf_execution')
    assert db.get(PerfTask,task.id).status=='running'
    assert db.query(PerfRun).filter_by(execution_key='second').one().snapshot['rps'] is None


def test_clear_cancelled_run_preserves_recovery_owner_until_control_is_idle(perf_control):
    perf,db,(task,_),cache,_response=perf_control
    finish(db,task,'first')
    repo.db_update(db,task.id,1,status='cancelled')
    cache.set(perf.RUN_LOCK_KEY,f'1:{task.id}:first')
    cache.set(perf.ACTIVE_RUN_KEY,f'1:{task.id}')
    cache.set(perf.CONTROL_LOCK_KEY,'another-control-request')
    with pytest.raises(perf.PerfControlUnavailableError):
        perf.s_clear_runs(db,task.id,1,PerfRunClear(all_finished=True))
    assert task.status=='cancelled' and db.query(PerfRun).count()==1
    assert cache.get(perf.RUN_LOCK_KEY)==f'1:{task.id}:first'
    cache.delete(perf.CONTROL_LOCK_KEY)
    assert perf.s_clear_runs(db,task.id,1,PerfRunClear(all_finished=True))==1
    assert cache.get(perf.RUN_LOCK_KEY) is None
    assert perf.s_mark_queued(db,task.id,1,'second').status=='queued'


def test_delete_definition_deletes_its_history_without_touching_other_tasks(perf_control):
    perf,db,(task,other),cache,_response=perf_control
    finish(db,task,'first');finish(db,other,'other')
    assert perf.s_delete(db,task.id,1) is not None
    assert db.query(PerfRun).count()==1 and db.query(PerfRun).one().task_id==other.id
    assert db.get(PerfTask,other.id) is not None


def test_migration_backfills_legacy_results_once_and_keeps_source_rows():
    engine=create_engine('sqlite:///:memory:');PerfTask.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([PerfTask(id=i,name='legacy',target_host='http://fixture.invalid',target_path='/orders',users=2,
            spawn_rate=1,duration=20,project_id=1,status=status,rps=12,request_stats=[{'num_requests':123}])
            for i,status in [(1,'done'),(2,'pending')]]);db.commit()
    ensure_perf_run_schema(engine);ensure_perf_run_schema(engine)
    with Session(engine) as db:
        assert db.query(PerfTask).count()==2
        run=db.query(PerfRun).one()
        assert run.snapshot['request_stats']==[{'num_requests':123}] and run.snapshot['rps']==12
        assert run.execution_key=='legacy:1' and run.status=='done'
    engine.dispose()


def test_tps_distinguishes_cumulative_success_and_interval_rates():
    first=transaction_sample({'iterations':100,'failures':10,'elapsed_seconds':10})
    second=transaction_sample({'iterations':160,'failures':20,'elapsed_seconds':12},first)
    assert first['avg_tps']==10 and first['success_tps']==9
    assert second['avg_tps']==pytest.approx(160/12)
    assert second['tps']==30 and second['current_success_tps']==25
    assert second['transaction_fail_ratio']==.125
    assert transaction_sample({'iterations':0,'failures':0,'elapsed_seconds':2})['tps']==0
    assert transaction_sample({})=={}
    assert transaction_sample({'iterations':3,'failures':4,'elapsed_seconds':2})=={}
    assert transaction_sample({'iterations':1,'failures':0,'elapsed_seconds':3},first)['tps'] is None


def test_setup_sql_cannot_erase_platform_execution_history():
    from app.core.sql_runner import validate_setup_sql
    with pytest.raises(ValueError):validate_setup_sql('DELETE FROM perf_runs WHERE id=1')


def test_history_http_pagination_authorization_config_snapshot_and_clear(notifications, monkeypatch):
    from app.routers.perf import router
    from app.services import perf
    from tests.test_perf_lifecycle import _ControlRedis
    monkeypatch.setattr(perf.redis, 'from_url', lambda _: _ControlRedis())
    client,db,_calls=notifications
    client.app.include_router(router)
    headers={'X-Project-Id':'1'}
    config={'name':'synthetic perf','target_host':'http://fixture.invalid','target_path':'/orders',
            'users':2,'spawn_rate':1,'duration':10,'load_config':{'steps':[{'name':'查询订单','path':'/orders'}]}}
    response=client.post('/perf/tasks',json=config,headers=headers)
    assert response.status_code==201,response.text
    task=db.get(PerfTask,response.json()['data']['id']);finish(db,task,'first');finish(db,task,'second')
    page=client.get(f'/perf/tasks/{task.id}/runs?limit=1',headers=headers).json()['data']
    assert page['total']==2 and len(page['items'])==1
    run_id=page['items'][0]['id']
    update=client.put(f'/perf/tasks/{task.id}',json={**config,'users':10},headers=headers)
    assert update.status_code==200,update.text
    result=client.get(f'/perf/tasks/{task.id}/runs/{run_id}',headers=headers)
    assert result.json()['data']['result']['users']==2
    other=client.get(f'/perf/tasks/{task.id}/runs/{run_id}',headers={'X-Project-Id':'3','X-Test-User':'4'})
    assert other.status_code==404
    readonly=client.post(f'/perf/tasks/{task.id}/runs/clear',json={'all_finished':True},headers={**headers,'X-Test-User':'3'})
    assert readonly.status_code==403
    clear=client.post(f'/perf/tasks/{task.id}/runs/clear',json={'run_ids':[run_id]},headers=headers)
    assert clear.status_code==200 and clear.json()['data']['deleted']==1
    assert db.get(PerfTask,task.id).users==10
    listing=client.get('/perf/tasks',headers=headers).json()['data']
    assert listing[0]['history_count']==1
    repo.db_update_if_status(db,task.id,1,task.status,status='queued',celery_task_id='stop-http')
    stopped=client.post(f'/perf/tasks/{task.id}/stop?execution_id=stop-http',headers=headers)
    assert stopped.status_code==200,stopped.text
    assert stopped.json()['data']['history_count']==2
    assert stopped.json()['data']['latest_run_id'] is not None
    assert client.post(f'/perf/tasks/{task.id}/runs/clear',json={},headers=headers).status_code==422
