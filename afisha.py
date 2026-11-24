"""Еженедельная афиша в ветку «Афиша» (тема 31): обложка (рендер) + подпись, закреп текущей, откреп прошлой.
Файлы выпуска: afisha/<дата четверга>/post.json + фон bg.jpg. Запуск: ISSUE=afisha/2026-11-26 [DRY_RUN=1] python afisha.py"""
import json, os, re, sys, datetime as dt, pathlib
from bot import tg, log, CHAT_ID
from afisha_render import render
HERE = pathlib.Path(__file__).parent
THREAD = int(os.environ.get("AFISHA_THREAD_ID", "31"))
def visible(h): return re.sub(r"<[^>]+>", "", h).replace("&amp;", "&")
def check(p, reg, d):
    errs, cap = [], p["caption"]
    if any(x["issue"] == d.name for x in reg["posted"]): errs.append("этот выпуск уже публиковался")
    if not 3 <= len(p["events"]) <= 5: errs.append("событий должно быть 3-5")
    if len(visible(cap)) > 1024: errs.append(f"подпись {len(visible(cap))} знаков, лимит 1024")
    if "!" in visible(cap) or "—" in cap or "–" in cap: errs.append("восклицательный знак или длинное тире")
    if cap.count("google.com/maps") < len(p["events"]) - 1: errs.append("не у всех событий ссылка на карту")
    if "Фон:" not in cap: errs.append("нет строки об авторе фона")
    if not (d / "bg.jpg").exists(): errs.append("нет bg.jpg")
    if "#" in visible(cap): errs.append("в афише без хэштегов")
    return errs
def main():
    d = HERE / os.environ["ISSUE"].strip()
    p = json.loads((d / "post.json").read_text())
    reg_p = HERE / "afisha" / "registry.json"
    reg = json.loads(reg_p.read_text()) if reg_p.exists() else {"posted": []}
    errs = check(p, reg, d); log(visible(p["caption"]))
    if errs: log("ОШИБКИ: " + "; ".join(errs)); sys.exit(1)
    cover = d / "cover.jpg"; render(p, d / "bg.jpg", cover); log(f"обложка {cover}")
    if os.environ.get("DRY_RUN", "0") == "1": log("dry run: проверки пройдены"); return
    r = tg("sendPhoto", dict(data=dict(chat_id=CHAT_ID, message_thread_id=THREAD, caption=p["caption"], parse_mode="HTML"),
                             files={"photo": ("cover.jpg", cover.read_bytes(), "image/jpeg")}))
    res = r.json(); log(r.text[:300])
    if not res.get("ok"): sys.exit(1)
    mid = res["result"]["message_id"]
    tg("pinChatMessage", dict(chat_id=CHAT_ID, message_id=mid, disable_notification=True))
    if reg["posted"]: tg("unpinChatMessage", dict(chat_id=CHAT_ID, message_id=reg["posted"][-1]["message_id"]))
    reg["posted"].append(dict(issue=d.name, dates=p["dates"], message_id=mid, at=dt.datetime.now(dt.timezone.utc).isoformat()))
    reg_p.write_text(json.dumps(reg, ensure_ascii=False, indent=2)); log(f"опубликовано, сообщение {mid}")
if __name__ == "__main__":
    main()
