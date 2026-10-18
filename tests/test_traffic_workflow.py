"""User-driven debug capture and replay; synthetic SQLite and mocked downstream HTTP."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models.traffic_capture import TrafficCapture
from app.models.traffic_record import TrafficRecord
from app.models.environment import Environment
from app.models.interface import Interface
from app.services import traffic_capture as capture, traffic_replay as replay, execution
from app.repositories import traffic_record as records
from app.routers import traffic_record as record_router, traffic_replay as replay_router
from app.core.migrations import ensure_traffic_capture_schema
from tests.test_suite_service import db


def snapshot(db, *, pid=1, uid=1, path='/orders/123', headers=None, params=None, body=None, response=None):
    state = capture.start(db, pid, uid)
    warning = capture.save_debug(db, project_id=pid, user_id=uid, capture_id=state['capture_id'],
        interface=SimpleNamespace(name='查询单个订单'),
        request={'method':'GET','url':'http://orders.invalid/api'+path,'headers':headers or {},'params':params,'body':body},
        response={'status_code':200,'body':response or {'amount':120}}, duration_ms=14,base_url='http://orders.invalid/api')
    assert warning is None
    return records.db_list(db,pid)[0]


def test_capture_is_owned_durable_idempotent_and_expiring(db):
    first = capture.start(db,1,1)
    assert first['active'] and first['count'] == 0
    assert capture.start(db,1,1)['capture_id'] == first['capture_id']
    assert capture.state(db,1,2)['active'] is False
    assert capture.state(db,2,1)['active'] is False
    db.expire_all()
    assert capture.state(db,1,1)['active'] is True
    assert capture.stop(db,1,2)['active'] is False
    assert capture.state(db,1,1)['active'] is True
    assert capture.stop(db,1,1)['active'] is False
    second = capture.start(db,1,1)
    assert first['capture_id'] != second['capture_id']
    db.get(TrafficCapture,(1,1)).expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert capture.active(db,1,1) is None
    assert capture.state(db,1,1)['active'] is False


def test_actual_path_query_and_response_are_saved_and_cross_field_secrets_masked(db):
    secret='synthetic-private-token'
    row=snapshot(db,path='/auth/login',headers={'Authorization':'Bearer '+secret},
        params={'token':secret,'echo':secret,'page':2},body={'password':secret},response={'token':secret,'echo':secret})
    assert row.path=='/auth/login' and row.source=='debug'
    assert row.request_params['page']==2 and row.duration_ms==14
    assert secret not in json.dumps({field:getattr(row,field) for field in ('request_headers','request_params','request_body','response_body')})
    assert row.response_body=={'token':'***','echo':'***'}
    assert records.db_get(db,row.id,2) is None
    assert capture.state(db,1,1)['count']==1


def test_stop_and_new_session_discard_inflight_old_response(db):
    initial=capture.start(db,1,1)
    capture.stop(db,1,1)
    for restart in (False,True):
        if restart:capture.start(db,1,1)
        assert capture.save_debug(db,project_id=1,user_id=1,capture_id=initial['capture_id'],interface=SimpleNamespace(name='old'),request={},response={},duration_ms=1)
    assert records.db_list(db,1)==[]


def test_size_and_record_caps_do_not_create_partial_records(db,monkeypatch):
    state=capture.start(db,1,1)
    kwargs=dict(db=db,project_id=1,user_id=1,capture_id=state['capture_id'],interface=SimpleNamespace(name='large'),request={'url':'http://orders.invalid/orders','method':'GET','body':'x'*70000},response={'status_code':200,'body':{}},duration_ms=1)
    assert '64 KB' in capture.save_debug(**kwargs)
    assert records.db_list(db,1)==[]
    monkeypatch.setattr(capture,'MAX_RECORDS',0)
    assert '上限' in capture.save_debug(**kwargs)


def test_debug_execution_records_only_active_owner_and_failure_is_nonfatal(db,monkeypatch):
    interface=Interface(name='查询订单',method='GET',url='/orders/{id}',path_params={'id':'123'},project_id=1,params={'page':2})
    env=Environment(name='local',base_url='http://orders.invalid/api',project_id=1,variables={})
    db.add_all([interface,env]);db.commit()
    response=requests.Response();response.status_code=200;response._content=b'{"amount":120}';response.headers['Content-Type']='application/json'
    downstream=Mock(return_value=response);monkeypatch.setattr(execution,'_request',downstream)
    assert execution.run_interface(db,interface.id,env.id,1,recording_user_id=1)['passed']
    assert records.db_list(db,1)==[]
    capture.start(db,1,2)
    execution.run_interface(db,interface.id,env.id,1,recording_user_id=1)
    assert records.db_list(db,1)==[]
    capture.start(db,1,1)
    output=execution.run_interface(db,interface.id,env.id,1,recording_user_id=1)
    assert output['passed'] and records.db_list(db,1)[0].path=='/orders/123'
    assert downstream.call_args.kwargs['url']=='http://orders.invalid/api/orders/123'
    monkeypatch.setattr(capture,'save_debug',Mock(side_effect=RuntimeError('private SQL')))
    output=execution.run_interface(db,interface.id,env.id,1,recording_user_id=1)
    assert output['passed'] and '保存失败' in output['recording_warning']
    assert 'private SQL' not in json.dumps(output)


@pytest.fixture
def replayer(db,monkeypatch):
    row=snapshot(db,headers={'Authorization':'Bearer synthetic-captured-secret','Content-Type':'application/json'},params={'page':2},body={'product_id':1})
    env=Environment(name='target',base_url='http://target.invalid/api',project_id=1,variables={'token':'synthetic-new-token'})
    db.add(env);db.commit()
    response=requests.Response();response.status_code=200;response._content=b'{"amount":120}'
    send=Mock(return_value=response);monkeypatch.setattr(replay.requests,'request',send)
    return row,env,response,send


def test_replay_requires_environment_and_replacement_for_redacted_credentials(db,replayer):
    row,env,response,send=replayer
    for env_id in (None,999):
        with pytest.raises(ValueError):replay.s_replay(db,row.id,1,env_id)
    with pytest.raises(ValueError,match='脱敏'):replay.s_replay(db,row.id,1,env.id)
    send.assert_not_called()
    result=replay.s_replay(db,row.id,1,env.id,overrides={'headers':{'Authorization':'Bearer ${token}'},'body':None})
    sent=send.call_args.kwargs
    assert sent['url']=='http://target.invalid/api/orders/123' and sent['params']=={'page':2}
    assert sent['headers']['authorization']=='Bearer synthetic-new-token' and sent['json'] is None
    assert sent['allow_redirects'] is False and sent['headers']['X-Shadow']=='1'
    assert 'X-Shadow-Authorization' not in sent['headers']
    assert result['diff']['same'] is True
    assert row.request_body=={'product_id':1}  # overrides never update the record


def test_replay_status_difference_and_new_secrets_are_not_hidden(db,replayer):
    row,env,response,send=replayer
    response.status_code=401
    response._content=b'{"token":"new-response-secret","echo":"new-response-secret"}'
    result=replay.s_replay(db,row.id,1,env.id,overrides={'headers':{'authorization':'Bearer ${token}'}})
    assert result['diff']['same'] is False
    assert result['diff']['diffs'][0]['path']=='(HTTP 状态码)'
    assert 'new-response-secret' not in json.dumps(result)


def test_replay_network_errors_and_unresolved_variables_never_expose_secrets(db,replayer):
    row,env,response,send=replayer
    with pytest.raises(ValueError,match='变量'):replay.s_replay(db,row.id,1,env.id,overrides={'headers':{'Authorization':'Bearer ${missing}'}})
    send.assert_not_called()
    send.side_effect=requests.ConnectionError('synthetic-new-token')
    with pytest.raises(ValueError,match='网络') as error:replay.s_replay(db,row.id,1,env.id,overrides={'headers':{'Authorization':'Bearer ${token}'}})
    assert 'synthetic-new-token' not in str(error.value)
    assert replay.s_replay(db,row.id,2,env.id) is None


def test_replay_large_response_cannot_pass_as_null(db,replayer):
    row,env,response,send=replayer
    row.response_body=None;db.commit();response._content=b'x'*70000
    result=replay.s_replay(db,row.id,1,env.id,overrides={'headers':{'authorization':'test'}})
    assert result['body_truncated'] and not result['diff']['same']


def test_list_pagination_and_capture_filter_are_stable(db):
    first=snapshot(db);capture.stop(db,1,1);second=snapshot(db)
    assert records.db_list(db,1,1,0)[0].id==second.id
    assert records.db_list(db,1,1,1)[0].id==first.id
    assert [row.id for row in records.db_list(db,1,100,0,first.capture_id)]==[first.id]


def test_migration_preserves_historical_rows_and_is_repeatable():
    engine=create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE project(id INTEGER PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE traffic_records(id INTEGER PRIMARY KEY,path VARCHAR(500))'))
        conn.execute(text("INSERT INTO traffic_records VALUES(1,'/demo/orders')"))
    ensure_traffic_capture_schema(engine);ensure_traffic_capture_schema(engine)
    assert {'capture_id','source','request_params','duration_ms'} <= {col['name'] for col in inspect(engine).get_columns('traffic_records')}
    with engine.connect() as conn:assert conn.execute(text('SELECT path FROM traffic_records')).scalar_one()=='/demo/orders'


def test_capture_routes_use_authenticated_user_and_validate_pagination(db):
    app=FastAPI();app.include_router(record_router.router);app.include_router(record_router.capture_router)
    context=SimpleNamespace(project_id=1,user=SimpleNamespace(id=1))
    for route in app.routes:
        for dependency in getattr(getattr(route,'dependant',None),'dependencies',[]):
            if dependency.name=='context':app.dependency_overrides[dependency.call]=lambda:context
    app.dependency_overrides[get_db]=lambda:db
    # SQLite db is bound to this thread; invoke pure handlers for writes, OpenAPI for contracts.
    assert record_router.capture_start(db,context)['data']['active']
    assert record_router.capture_stop(db,context)['data']['active'] is False
    schema=app.openapi()
    assert '/traffic/capture/start' in schema['paths']
    assert schema['paths']['/traffic/records']['get']['parameters'][0]['schema']['maximum']==100


def test_path_environment_secrets_and_url_userinfo_are_not_exposed(db):
    state=capture.start(db,1,1)
    assert capture.save_debug(db,project_id=1,user_id=1,capture_id=state['capture_id'],interface=SimpleNamespace(name='secret'),request={'method':'GET','url':'http://synthetic-user:synthetic-password@orders.invalid/orders/synthetic-path-token'},response={'status_code':200,'body':{}},duration_ms=1,known_secrets={'synthetic-path-token'}) is None
    row=records.db_list(db,1)[0]
    assert row.path=='/orders/***' and row.target_host=='http://orders.invalid'
