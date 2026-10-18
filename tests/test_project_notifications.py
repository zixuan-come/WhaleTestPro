"""Real authorization and persistence, isolated DB; never contacts Feishu."""
import base64
import hashlib
import hmac
import importlib
import pkgutil
from types import SimpleNamespace

import pytest
import requests
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models as app_models
from app.database import Base, get_db
from app.core.authentication import get_current_user
from app.core import notifier
from app.core.exception_handlers import http_exception_handler, validation_exception_handler
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
from app.models.user import User
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.project import Project
from app.models.project_notification import ProjectNotification
from app.routers.project import router
from app.schemas.project_notification import NotificationUpdate
from app.services import project_notification as service

URL = 'https://open.feishu.cn/open-apis/bot/v2/hook/11111111-2222-3333-4444-555555555555'
OTHER_URL = 'https://open.feishu.cn/open-apis/bot/v2/hook/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


@pytest.fixture
def notifications(monkeypatch):
    for module in pkgutil.iter_modules(app_models.__path__):
        importlib.import_module('app.models.' + module.name)
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.execute(text('PRAGMA foreign_keys=ON'))
    db.add_all([User(id=i, username=f'notify-user-{i}', hashed_password='unused') for i in (1,2,3,4)])
    db.flush();db.add_all([Team(id=1,name='notify-team',owner_id=1),Team(id=2,name='private-team',owner_id=4)])
    db.flush();db.add_all([TeamMember(team_id=1,user_id=i,role=role) for i,role in [(1,'owner'),(2,'admin'),(3,'member')]])
    db.add(TeamMember(team_id=2,user_id=4,role='owner'))
    db.add_all([Project(id=i,name=f'notify-project-{i}',team_id=2 if i==3 else 1) for i in (1,2,3)])
    db.commit()
    app = FastAPI();app.include_router(router)
    app.add_exception_handler(HTTPException,http_exception_handler)
    app.add_exception_handler(RequestValidationError,validation_exception_handler)
    app.dependency_overrides[get_db] = lambda:db
    def current_user(x_test_user: int = Header(1)):
        return db.get(User,x_test_user)
    app.dependency_overrides[get_current_user] = current_user
    calls=[]
    def downstream(url,**kwargs):
        calls.append((url,kwargs));return SimpleNamespace(status_code=200,json=lambda:{'code':0})
    monkeypatch.setattr(notifier.requests,'post',downstream)
    try:
        with TestClient(app) as client:yield client,db,calls
    finally:db.close();engine.dispose()


def save(client,**payload):
    return client.put('/projects/1/notifications',json={'enabled':True,'webhook_url':URL,**payload})


def test_admin_save_encrypts_and_all_reads_hide_credentials(notifications):
    client,db,calls=notifications
    response=client.put('/projects/1/notifications',headers={'X-Test-User':'2'},json={'enabled':True,'webhook_url':URL,'signing_secret':'private-signature'})
    assert response.status_code==200,response.text
    row=db.get(ProjectNotification,1)
    assert URL not in row.webhook_ciphertext and 'private-signature' not in row.signing_secret_ciphertext
    assert service._credentials(db,1)==(URL,'private-signature')
    for path in ('/projects','/projects/1','/projects/1/notifications'):
        reply=client.get(path)
        assert reply.status_code==200,reply.text
        assert URL not in reply.text and 'private-signature' not in reply.text and 'ciphertext' not in reply.text
    assert not calls


def test_members_read_status_but_cannot_modify_or_send_test_and_outsiders_cannot_access(notifications):
    client,db,calls=notifications
    assert save(client).status_code==200
    headers={'X-Test-User':'3'}
    reply=client.get('/projects/1/notifications',headers=headers)
    assert reply.json()['data']=={'enabled':True,'configured':True,'signing_configured':False,'can_manage':False}
    assert client.put('/projects/1/notifications',headers=headers,json={'enabled':False}).status_code==403
    assert client.post('/projects/1/notifications/test',headers=headers).status_code==403
    for method,path in [('get','/projects/3/notifications'),('put','/projects/3/notifications'),('post','/projects/3/notifications/test')]:
        kwargs={'json':{'enabled':False}} if method=='put' else {}
        assert getattr(client,method)(path,**kwargs).status_code==404
    assert not calls


def test_empty_fields_preserve_credentials_explicit_clear_removes_them(notifications):
    client,db,_=notifications
    assert save(client,signing_secret='keep-secret').status_code==200
    assert client.put('/projects/1/notifications',json={'enabled':False,'webhook_url':'','signing_secret':''}).status_code==200
    assert service._credentials(db,1,False)==(URL,'keep-secret')
    assert client.put('/projects/1/notifications',json={'enabled':False,'clear_signing_secret':True}).status_code==200
    assert service._credentials(db,1,False)==(URL,None)
    assert client.put('/projects/1/notifications',json={'enabled':True,'clear_webhook':True}).status_code==422
    assert client.put('/projects/1/notifications',json={'enabled':False,'clear_webhook':True}).status_code==200
    assert not db.get(ProjectNotification,1).webhook_ciphertext


@pytest.mark.parametrize('url',[
    'http://open.feishu.cn/open-apis/bot/v2/hook/'+('a'*32),
    'https://127.0.0.1/private','https://open.feishu.cn.evil.invalid/open-apis/bot/v2/hook/'+('a'*32),
    'https://user@open.feishu.cn/open-apis/bot/v2/hook/'+('a'*32),URL+'?secret=leak',URL+'#leak',
    URL.replace('https://','https://\n'),URL.replace('feishu.cn','feishu.cn:443'),URL+'/extra',
])
def test_invalid_destinations_are_rejected_without_leaking_or_sending(notifications,url):
    client,db,calls=notifications
    reply=save(client,webhook_url=url)
    assert reply.status_code==422 and url not in reply.text
    assert db.get(ProjectNotification,1) is None and not calls


def test_signed_test_message_checks_saved_config_and_notification_errors_are_safe(notifications,monkeypatch):
    client,db,calls=notifications
    assert save(client,signing_secret='sample-key').status_code==200
    monkeypatch.setattr(notifier.time,'time',lambda:1599360473)
    reply=client.post('/projects/1/notifications/test');assert reply.status_code==200
    url,request=calls[-1];assert url==URL and request['timeout']==(3,5) and request['allow_redirects'] is False
    payload=request['json'];assert 'WhaleTestPro' in payload['content']['text'] and 'notify-project-1' in payload['content']['text']
    expected=base64.b64encode(hmac.new(b'1599360473\nsample-key',digestmod=hashlib.sha256).digest()).decode()
    assert payload['timestamp']=='1599360473' and payload['sign']==expected
    monkeypatch.setattr(notifier.requests,'post',lambda *a,**k:(_ for _ in ()).throw(requests.Timeout(URL)))
    reply=client.post('/projects/1/notifications/test')
    assert reply.status_code==400 and URL not in reply.text


@pytest.mark.parametrize('body,status',[({'code':19024},200),({'code':19021},200),({'code':11232},200),({'code':[]},200),({},200),({'code':0},302),({'code':0},500)])
def test_http_and_business_failures_are_not_reported_as_success(notifications,monkeypatch,body,status):
    client,_,_=notifications;assert save(client).status_code==200
    monkeypatch.setattr(notifier.requests,'post',lambda *a,**k:SimpleNamespace(status_code=status,json=lambda:body))
    assert client.post('/projects/1/notifications/test').status_code==400


def test_project_routing_disabled_missing_config_and_no_global_fallback(notifications,monkeypatch):
    client,db,calls=notifications
    monkeypatch.setattr(settings,'FEISHU_WEBHOOK',OTHER_URL)
    summary={'total':1,'passed_count':1,'pass_rate':1,'interface_coverage':1}
    service.notify_regression(db,1,summary)
    assert not calls and '尚未配置' in summary['notification_warning']
    save(client)
    service.save(db,2,NotificationUpdate(enabled=True,webhook_url=OTHER_URL))
    service.notify_regression(db,2,summary)
    assert calls[-1][0]==OTHER_URL
    client.put('/projects/1/notifications',json={'enabled':False})
    calls.clear();service.notify_regression(db,1,summary)
    assert not calls and '已停用' in summary['notification_warning']
    # Saved configuration can be tested before enabling automatic notifications.
    assert client.post('/projects/1/notifications/test').status_code==200


def test_ciphertext_cannot_be_moved_between_projects_and_migration_is_idempotent(notifications):
    client,db,_=notifications;save(client)
    db.add(ProjectNotification(project_id=2,feishu_enabled=True,webhook_ciphertext=db.get(ProjectNotification,1).webhook_ciphertext));db.commit()
    with pytest.raises(notifier.NotificationDeliveryError,match='无法读取'):service._credentials(db,2)
    from app.core.migrations import ensure_project_notification_schema
    ensure_project_notification_schema(db.bind);ensure_project_notification_schema(db.bind)
    assert db.query(ProjectNotification).count()==2
    assert inspect(db.bind).get_foreign_keys('project_notification')[0]['options']['ondelete']=='CASCADE'
