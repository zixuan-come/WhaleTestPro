import contextvars

# 默认False（默认是真实流量，不是影子）
_shadow_flag: contextvars.ContextVar[bool] = contextvars.ContextVar("shadow_flag", default=False)

# 写：中间件在入口处调用，把这个请求标成影子/非影子
def set_shadow(value: bool) -> None:
    _shadow_flag.set(value)

# 读：database.py 的 get_bind 每次选库时调用，问"现在是不是影子"
def is_shadow() -> bool:
    return _shadow_flag.get()












