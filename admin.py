"""Разовые админ-действия бота по файлу admin/<имя>.json: список шагов {method, params}.
Разрешены только безопасные методы, чат фиксирован. В params можно писать "$thread" (id ветки,
созданной шагом createForumTopic) и "$msg<N>" (message_id ответа шага N, с нуля).
Запуск: ACTIONS_FILE=admin/x.json [DRY_RUN=1] python admin.py"""
import json, os, sys, pathlib
from bot import tg, log, CHAT_ID
ALLOWED = {"createForumTopic", "sendMessage", "pinChatMessage", "unpinChatMessage", "deleteMessage", "sendPhoto", "editForumTopic"}
HERE = pathlib.Path(__file__).parent

def subst(v, ctx):
    if isinstance(v, str) and v.startswith("$") and v[1:] in ctx: return ctx[v[1:]]
    if isinstance(v, dict): return {k: subst(x, ctx) for k, x in v.items()}
    return v

def main():
    steps = json.loads((HERE / os.environ["ACTIONS_FILE"].strip()).read_text())
    for s in steps:
        if s["method"] not in ALLOWED: log(f"метод не разрешён: {s['method']}"); sys.exit(1)
    if os.environ.get("DRY_RUN", "0") == "1":
        log(json.dumps(steps, ensure_ascii=False, indent=1)[:3000]); log("dry run ок"); return
    ctx = {}
    for i, s in enumerate(steps):
        p = dict(subst(s.get("params", {}), ctx), chat_id=CHAT_ID)
        r = tg(s["method"], p); res = r.json(); log(f"шаг {i} {s['method']}: {r.text[:300]}")
        if not res.get("ok"):
            if s.get("optional"): continue
            sys.exit(1)
        out = res.get("result")
        if isinstance(out, dict):
            if "message_thread_id" in out and s["method"] == "createForumTopic": ctx["thread"] = out["message_thread_id"]
            if "message_id" in out: ctx[f"msg{i}"] = out["message_id"]

if __name__ == "__main__":
    main()
