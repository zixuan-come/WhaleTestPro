"""Live samples must be committed before termination; synthetic Locust control only."""
from types import SimpleNamespace
from sqlalchemy.orm import Session
import pytest
from app.models.perf import PerfTask
from tests.test_perf_lifecycle import perf_control


def test_samples_are_visible_to_another_reader_while_running(perf_control,monkeypatch):
    perf,db,(task,_),cache,response=perf_control
    task.duration=6;db.commit();perf.s_mark_queued(db,task.id,1,'live')
    count=0;observed=[]
    def get(base,path):
        nonlocal count
        if path=='/whale/iterations':return {'lease':cache.get(perf.RUN_LOCK_KEY),'configuration_failures':0}
        count+=1
        return {'total_rps':count*2,'fail_ratio':0.1,'user_count':2,'stats':[
            {'name':'Aggregated','num_requests':count*10,'avg_response_time':20,'response_time_percentile_0.95':40,'response_time_percentile_0.99':60},
            {'name':'step_01','method':'GET','num_requests':count*10,'num_failures':1,'current_rps':count*2,'avg_response_time':20}]}
    monkeypatch.setattr(perf,'_control_get_json',get)
    monkeypatch.setattr(perf.requests,'post',lambda *a,**k:response)
    monkeypatch.setattr(perf,'MAX_LIVE_HISTORY_SAMPLES',2)
    update=perf.perf_repo.db_update_if_status
    def publish(*args,**fields):
        result=update(*args,**fields)
        if 'history_samples' in fields and 'status' not in fields:
            with Session(db.get_bind()) as reader:
                row=reader.get(PerfTask,task.id)
                observed.append({'status':row.status,'rps':row.rps,'requests':row.request_stats[0]['num_requests'],'history':len(row.history_samples),'p95':row.p95_response_ms})
        return result
    monkeypatch.setattr(perf.perf_repo,'db_update_if_status',publish)
    result=perf.s_run(db,task.id,1,'live')
    assert len(observed)==3 and all(row['status']=='running' for row in observed)
    assert [row['requests'] for row in observed]==[10,20,30]
    assert observed[-1]['history']==2 and observed[0]['p95']==40
    assert result.status=='done' and result.rps==6
    assert result.request_stats[0]['num_requests']==40


def test_empty_warmup_is_publishable_but_empty_final_run_is_not(perf_control):
    perf,*_=perf_control
    assert perf._result_statistics({},None,{},[],allow_empty=True)['request_stats'] is None
    with pytest.raises(perf.PerfControlUnavailableError):perf._result_statistics({},None,{},[])


def test_stop_preserves_published_sample_and_late_sample_cannot_revive_task(perf_control,monkeypatch):
    perf,db,(task,_),cache,response=perf_control
    task.duration=6;db.commit();perf.s_mark_queued(db,task.id,1,'stop-live')
    count=0
    def get(base,path):
        nonlocal count
        if path=='/whale/iterations':return {'lease':cache.get(perf.RUN_LOCK_KEY),'configuration_failures':0}
        count+=1
        if count==2:perf.s_cancel(db,task.id,1)
        return {'total_rps':5,'stats':[{'name':'Aggregated','num_requests':count*10},{'name':'step_01','method':'GET','num_requests':count*10}]}
    monkeypatch.setattr(perf,'_control_get_json',get);monkeypatch.setattr(perf.requests,'post',lambda *a,**k:response)
    result=perf.s_run(db,task.id,1,'stop-live')
    assert result.status=='cancelled' and result.request_stats[0]['num_requests']==10
    assert len(result.history_samples)==1
