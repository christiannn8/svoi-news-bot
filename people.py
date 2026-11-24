"""Посты ветки «Свои люди» (тема 12). Источник правды: Google-таблица «Свои люди · база специалистов».
Задача Claude берёт из таблицы строки «утверждено» + «Опубликовано = нет», пишет people/<дата>-<категория>.json и запускает
workflow svoi-people. Бот только проверяет и публикует.
Запуск: POST_FILE=people/xxx.json [DRY_RUN=1] python people.py ; удаление: DELETE_MESSAGE_IDS="1,2" python people.py"""
import json, os, re, sys, datetime as dt, pathlib
from bot import tg, log, CHAT_ID

HERE = pathlib.Path(__file__).parent
THREAD = int(os.environ.get("PEOPLE_THREAD_ID", "12"))

def visible(html):
    return re.sub(r"<[^>]+>", "", html).replace("&amp;", "&")

def check(p, registry):
    errs, text = [], p["text"]
    done = {i for x in registry["posted"] for i in x["ids"]}
    if not 1 <= len(p["ids"]) <= 5: errs.append("в посте должно быть от 1 до 5 специалистов")
    if set(p["ids"]) & done: errs.append(f"уже публиковались: {sorted(set(p['ids']) & done)}")
    if len(visible(text)) > 4000: errs.append("длиннее лимита Telegram")
    if "!" in visible(text): errs.append("восклицательный знак")
    if "—" in text or "–" in text: errs.append("длинное тире")
    if not text.startswith("❤️ <b>Свои люди:"): errs.append("нет заголовка «Свои люди: ...»")
    if text.count("Источник") < len(p["ids"]): errs.append("у каждого специалиста нужна ссылка на источник")
    if "Вопросы и помощь" not in text: errs.append("нет призыва порекомендовать специалиста")
    return errs

def main():
    del_ids = os.environ.get("DELETE_MESSAGE_IDS", "").strip()
    if del_ids:
        for mid in [int(x) for x in del_ids.split(",") if x.strip()]:
            log(f"удаление {mid}: {tg('deleteMessage', dict(chat_id=CHAT_ID, message_id=mid)).text[:200]}")
        return
    pf = HERE / os.environ["POST_FILE"].strip()
    p = json.loads(pf.read_text())
    reg_p = HERE / "people" / "registry.json"
    registry = json.loads(reg_p.read_text()) if reg_p.exists() else {"posted": []}
    errs = check(p, registry)
    log("пост:\n" + visible(p["text"]))
    if errs: log("ОШИБКИ: " + "; ".join(errs)); sys.exit(1)
    if os.environ.get("DRY_RUN", "0") == "1": log("dry run: проверки пройдены"); return
    r = tg("sendMessage", dict(chat_id=CHAT_ID, message_thread_id=THREAD, text=p["text"], parse_mode="HTML",
                               link_preview_options={"is_disabled": True}))
    log(r.text[:300]); res = r.json()
    if not res.get("ok"): sys.exit(1)
    mid = res["result"]["message_id"]
    registry["posted"].append(dict(file=pf.name, ids=p["ids"], category=p.get("category", ""), message_id=mid,
                                   at=dt.datetime.now(dt.timezone.utc).isoformat()))
    reg_p.write_text(json.dumps(registry, ensure_ascii=False, indent=2))
    log(f"опубликовано, сообщение {mid}")

if __name__ == "__main__":
    main()
