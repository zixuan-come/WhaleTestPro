from sqlalchemy import text
from app.core.variables import extract
from jsonschema import validate
from jsonschema.exceptions import ValidationError

def run_assertions(response, assertions, db):
    results = []
    for a in assertions or []:
        a_type = a["type"]
        try:
            if a_type == "json_eq":
                actual = extract(response.json(), a["path"])
                passed = actual == a["expected"]
            elif a_type == "json_contains":
                actual = extract(response.json(), a["path"])
                passed = a["expected"] in actual
            elif a_type == "json_gt":
                actual = extract(response.json(), a["path"])
                passed = actual > a["expected"]
            elif a_type == "json_lt":
                actual = extract(response.json(), a["path"])
                passed = actual < a["expected"]
            elif a_type == "response_time_lt":
                actual = response.elapsed.total_seconds() * 1000
                passed = actual < a["expected"]
            elif a_type == "header_eq":
                actual = response.headers.get(a["path"])
                passed = actual == a["expected"]
            elif a_type == "header_contains":
                actual = response.headers.get(a["path"])
                passed = a["expected"] in actual
            elif a_type == "json_schema":
                validate(instance=response.json(), schema=a["expected"])
                actual = "schema 校验通过"
                passed = True
            elif a_type == "db_eq":
                actual = db.execute(text(a["sql"])).scalar()
                passed = actual == a["expected"]
            else:
                actual = f"未知断言类型: {a_type}"
                passed = False
        except ValidationError as e:
            actual = f"schema 校验失败: {e.message}"
            passed = False
        except Exception as e:
            actual = f"断言执行出错: {e}"
            passed = False

        results.append({
            "type": a_type,
            "passed": passed,
            "expected": a.get("expected"),
            "actual": actual,
        })

    return results












