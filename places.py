"""Посты ветки «Где, что и как в Афинах»: альбом фото + подпись, реестр мест без повторов.
Запуск: PLACE_SLUG=<папка в places/> [DRY_RUN=1] python places.py
Удаление: DELETE_MESSAGE_IDS="12,13,14" python places.py"""
import json, os, re, sys, datetime as dt, pathlib
from bot import tg, log, CHAT_ID

HERE = pathlib.Path(__file__).parent
PLACES = HERE / "places"
THREAD = int(os.environ.get("PLACES_THREAD_ID", "8"))
WHAT = "#где_поесть #кофе #с_детьми #пляжи #рынки #прогулки #достопримечательности #спорт #транспорт #документы #коммуналка #быт".split()
WHERE = "#Пирей #Палео_Фалиро #Алимос #Каламаки #Агиос_Димитриос #Аргируполи #Элиникон #Глифада #Вула #Вульягмени #Афины".split()

def visible(html):
    return re.sub(r"<[^>]+>", "", html).replace("&amp;", "&")

def check(p, registry):
    errs, cap = [], p["caption"]
    if any(x["slug"] == p["slug"] for x in registry["posted"]): errs.append("место уже публиковалось")
    if len(visible(cap)) > 1024: errs.append(f"подпись {len(visible(cap))} знаков, лимит 1024")
    if "!" in visible(cap): errs.append("восклицательный знак")
    if "—" in cap or "–" in cap: errs.append("длинное тире")
    if "google.com/maps" not in cap: errs.append("нет ссылки на Google Maps")
    if "Фото:" not in cap: errs.append("нет строки об авторах фото")
    if not 2 <= len(p["photos"]) <= 10: errs.append("фото должно быть от 2 до 10")
    tags = re.findall(r"#\w+", cap)
    bad = [t for t in tags if t not in WHAT + WHERE]
    if bad: errs.append(f"неутверждённые хэштеги: {bad}")
    if not any(t in WHAT for t in tags) or not any(t in WHERE for t in tags): errs.append("нужен хэштег «что» и хэштег «где»")
    for f in p["photos"]:
        if not (PLACES / p["slug"] / f).exists(): errs.append(f"нет файла {f}")
    return errs

def main():
    del_ids = os.environ.get("DELETE_MESSAGE_IDS", "").strip()
    if del_ids:
        for mid in [int(x) for x in del_ids.split(",") if x.strip()]:
            r = tg("deleteMessage", dict(chat_id=CHAT_ID, message_id=mid)); log(f"удаление {mid}: {r.text[:200]}")
        return
    slug = os.environ["PLACE_SLUG"].strip()
    p = json.loads((PLACES / slug / "post.json").read_text())
    reg_p = PLACES / "registry.json"; registry = json.loads(reg_p.read_text())
    errs = check(p, registry)
    log("подпись:\n" + visible(p["caption"]))
    if errs: log("ОШИБКИ: " + "; ".join(errs)); sys.exit(1)
    if os.environ.get("DRY_RUN", "0") == "1": log("dry run: проверки пройдены"); return

    media, files = [], {}
    for i, f in enumerate(p["photos"]):
        m = {"type": "photo", "media": f"attach://p{i}"}
        if i == 0: m.update(caption=p["caption"], parse_mode="HTML")
        media.append(m); files[f"p{i}"] = (f, open(PLACES / slug / f, "rb").read(), "image/jpeg")
    r = tg("sendMediaGroup", dict(data=dict(chat_id=CHAT_ID, message_thread_id=THREAD, media=json.dumps(media, ensure_ascii=False)), files=files))
    log(r.text[:500])
    res = r.json()
    if not res.get("ok"): sys.exit(1)
    ids = [m["message_id"] for m in res["result"]]
    registry["posted"].append(dict(slug=slug, name=p["name"], category=p["category"], area=p["area"],
        south=p.get("south", False), message_ids=ids, at=dt.datetime.now(dt.timezone.utc).isoformat()))
    reg_p.write_text(json.dumps(registry, ensure_ascii=False, indent=2))
    log(f"опубликовано, сообщения {ids}")

if __name__ == "__main__":
    main()
