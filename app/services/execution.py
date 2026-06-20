from app.repositories import case as case_repo
from app.repositories import interface as interface_repo
import requests

def run_case(db, case_id):
    case = case_repo.db_get(db, case_id)
    if case is None:
        return {"error": "用例不存在"}

    interface = interface_repo.db_get(db, case.interface_id)
    if interface is None:
        return {"error": "用例关联的接口不存在"}
    response = requests.request(method=interface.method, url=interface.url)
    passed = response.status_code == case.expected_status
    return {
        "passed": passed,
        "expected_status": case.expected_status,
        "actual_status": response.status_code
    }




