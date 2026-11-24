#!/usr/bin/env python3
"""Бот новостей «Свои на юге Афин»: одна новость в день в ветку «Новости».
Правила: см. RULES.md. Заголовок переводит DeepL. Пересказ и пункты «Что это значит для вас»
и «Что взять во внимание» пишет Claude (ежедневная задача): сначала запуск в режиме list показывает
кандидатов, затем запуск с force_url и ai_json публикует выбранную статью. Без ai_json бот не публикует."""
import html, json, os, re, sys, time, unicodedata, datetime as dt
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import feedparser, requests

HERE = Path(__file__).parent
CHAT_ID = int(os.environ.get("CHAT_ID", "-1004436423996"))
THREAD_ID = int(os.environ.get("THREAD_ID", "4"))
ALLOWED = ["#закон", "#налоги", "#аренда", "#недвижимость", "#документы", "#визы",
           "#транспорт", "#быт", "#цены", "#срочно", "#Греция", "#Афины", "#юг_Афин"]
TOPICS = {
 "#налоги": r"\btax|\baade\b|εφορ|φορολ|φόρο|φοροι|εισόδημα|income tax|vat\b|φπα",
 "#закон": r"\blaw\b|\bbill\b|legislat|parliament|ministerial decision|νόμο|νομοσχ|βουλή|υπουργική απόφαση",
 "#аренда": r"\brent\b|rental|tenant|landlord|ενοίκ|μίσθωσ|airbnb|short-term",
 "#недвижимость": r"real estate|propert|housing|mortgage|apartment|ακίνητ|στέγαση|στεγαστικ|κατοικία|spiti mou|σπίτι μου",
 "#документы": r"passport|certificate|residence permit|id card|afm|amka|πιστοποιητ|έγγραφ|ταυτότητα|αφμ|αμκα|gov\.gr",
 "#визы": r"\bvisa|residence permit|migrat|immigra|golden visa|asylum|βίζα|μετανάστ|άδεια διαμονής|άδειες διαμονής",
 "#транспорт": r"metro|\bbus\b|ferry|ferries|train|transport|airport|tram|taxi|μετρό|λεωφορ|συγκοινων|πλοί|τρένο|αεροδρόμ|οασα|στάση εργασίας",
 "#быт": r"electricity|water supply|utilit|school|hospital|health|garbage|ρεύμα|νερό|δήμο|σχολ|νοσοκομ|καθαριότητα|δεη",
 "#цены": r"\bprice|inflation|cost of living|wage|salary|τιμές|ακρίβεια|πληθωρισμ|μισθ",
 "#срочно": r"breaking|urgent|warning|red alert|civil protection|strike|storm|κακοκαιρία|πολιτική προστασία|απεργ|112",
}
GREECE = r"greece|greek|athens|attica|ελλάδ|ελλην|αθήν|αττικ"
ATHENS = r"athens|attica|αθήν|αττικ"
SOUTH = r"glyfada|voula|vouliagmeni|alimos|elliniko|ellinikon|palaio faliro|paleo faliro|argyroupol|vari\b|kalamaki|agios kosmas|γλυφάδα|βούλα|βουλιαγμένη|άλιμος|(?<!\w)ελληνικό(?!\w)|παλαιό φάληρο|αργυρούπολ|βάρη|καλαμάκι"
TAXLAW = {"#налоги", "#закон", "#визы"}
BOILER = re.compile(r"(the post .*? appeared first on .*|continue reading.*|read more.*|διαβάστε περισσότερα.*|το άρθρο .*? δημοσιεύθηκε .*)$", re.I | re.S)

def log(*a): print(*a, file=sys.stderr)

def norm_url(u):
    p = urlsplit(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), urlencode(q), ""))

def strip_html(s):
    s = re.sub(r"<(script|style).*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def plain(s):
    """нижний регистр без ударений: ΣΥΝΕΝΤΕΥΞΗ и συνέντευξη совпадают"""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()

JUNK = re.compile(r"σχετικο αρχειο|πραξη βεβαιωσης|προκηρυξη διαγωνισμ|διακηρυξη|συνεντευξ|interview|βιντεο|video:|live blog|podcast|ομιλια|speech|δηλωσ", re.I)
QUOTE_TITLE = re.compile(r"^[^:«\"“]{3,70}:\s*[«\"“]")

def sentences(text):
    text = BOILER.sub("", text).strip()
    parts = re.split(r"(?<=[.!?;…»”])\s+(?=[A-ZА-ЯΑ-Ωα-ωA-Za-z0-9«\"“])", text)
    return [p.strip() for p in parts if len(p.strip()) > 25]

def trim(sents, limit=700):
    out, n = [], 0
    for x in sents[:5]:
        if n + len(x) > limit and len(out) >= 4: break
        if len(x) > 300: continue  # слишком длинное «предложение» = склеенный текст
        out.append(x); n += len(x)
    return out

def tokens(ru_title):
    t = re.findall(r"[a-zа-яё0-9]+", ru_title.lower())
    stop = {"в", "на", "и", "по", "для", "с", "из", "от", "к", "о", "об", "за", "что", "как", "при", "до", "не"}
    return {w[:5] for w in t if w not in stop and len(w) > 2}

def numbers(s): return set(re.findall(r"\d[\d.,]*", s))

def is_dup(tok, nums, history):
    for h in history:
        ht, hn = set(h["tok"]), set(h.get("nums", []))
        if not tok or not ht: continue
        j = len(tok & ht) / len(tok | ht)
        if j >= 0.45 or (len(tok & ht) >= 3 and len(nums & hn) >= 2):
            return h
    return None

def deepl(texts, lang, key):
    if not key:
        return [f"[{lang}→ru] {t}" for t in texts]
    r = requests.post("https://api-free.deepl.com/v2/translate",
                      headers={"Authorization": f"DeepL-Auth-Key {key}"},
                      data={"text": texts, "target_lang": "RU", "source_lang": lang.upper()[:2],
                            "formality": "default"}, timeout=40)
    r.raise_for_status()
    return [x["text"] for x in r.json()["translations"]]

def fetch(feed):
    r = requests.get(feed["url"], timeout=30, headers={"User-Agent": "Mozilla/5.0 (SvoiNewsBot)"})
    r.raise_for_status()
    return feedparser.parse(r.content)

def candidates(feeds, now, max_age_h=72):
    out = []
    for f in feeds:
        try:
            parsed = fetch(f)
        except Exception as e:
            log("FEED FAIL", f["name"], e); continue
        for e in parsed.entries:
            link = e.get("link")
            if not link: continue
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if not ts: continue
            pub = dt.datetime(*ts[:6], tzinfo=dt.timezone.utc)
            if pub > now + dt.timedelta(hours=1) or now - pub > dt.timedelta(hours=max_age_h):
                continue  # будущее или старое
            body = ""
            if e.get("content"): body = e.content[0].get("value", "")
            if len(strip_html(body)) < len(strip_html(e.get("summary", ""))): body = e.get("summary", "")
            text = strip_html(body)
            title = strip_html(e.get("title", ""))
            blob = f"{title} {text}".lower()
            head = f"{title} {text[:350]}".lower()
            tags = [t for t, rx in TOPICS.items() if re.search(rx, head)]
            if f["tier"] == "A":
                tags = tags or [h for h in f["hashtags"] if h in ALLOWED and h not in ("#Греция", "#Афины", "#юг_Афин")]
            if not tags: continue
            if f["tier"] == "B" and not re.search(GREECE, blob): continue
            if len(title) > 160 or JUNK.search(plain(blob)) or QUOTE_TITLE.search(title): continue  # интервью, речи, цитаты, документы
            sents = [x for x in trim(sentences(text)) if x.count("«") + x.count("“") + x.count('"') < 2]
            if sents and plain(sents[0])[:60] == plain(title)[:60]: sents = sents[1:]  # первое предложение = заголовок
            if len(sents) < 4: continue
            place = ["#Греция"]
            if re.search(ATHENS, head) or "#Афины" in f["hashtags"]: place.append("#Афины")
            if re.search(SOUTH, head) or "#юг_Афин" in f["hashtags"]: place += ["#юг_Афин"] if "#Афины" in place else ["#Афины", "#юг_Афин"]
            score = (3 if f["tier"] == "A" else 0) + len({"#аренда", "#недвижимость", "#документы", "#визы", "#налоги"} & set(tags)) * 2 \
                    + (1 if "#юг_Афин" in place else 0) - (now - pub).total_seconds() / 86400
            out.append(dict(feed=f, title=title, link=link, url_n=norm_url(link), pub=pub.isoformat(),
                            text=BOILER.sub("", text)[:6000], sents=sents, tags=tags[:2], place=place, score=score))
    return sorted(out, key=lambda c: -c["score"])

def dash(t):  # без длинных тире, как во всех текстах «Свои»
    return re.sub(r"\s*[—–]\s*", " - ", (t or "").strip())

def build_post(c, title_ru, ai):
    tags = [t for t in c["tags"] + c["place"] if t in ALLOWED]
    note = " (по данным СМИ)" if c["feed"]["tier"] == "B" else ""
    src = f'Источник: <a href="{html.escape(c["link"], quote=True)}">{html.escape(c["feed"]["name"])}</a>{note}'
    e = lambda t: html.escape(dash(t))
    return (f"📰 <b>{e(title_ru)}</b>\n\n{e(ai['summary'])}\n\n"
            f"<b>Что это значит для вас:</b> {e(ai['meaning'])}\n\n"
            f"<b>Что взять во внимание:</b> {e(ai['attention'])}\n\n{src}\n{' '.join(tags)}")

def nsent(t): return len([x for x in re.split(r"(?<=[.!?…])\s+", (t or "").strip()) if len(x) > 3])

def check_ai(ai):
    errs = []
    if ai.get("skip"): return [f"модель пропустила: {ai.get('reason', '')}"]
    for k in ("summary", "meaning", "attention"):
        if not (ai.get(k) or "").strip(): errs.append(f"пусто: {k}")
        if "!" in (ai.get(k) or ""): errs.append(f"восклицательный знак: {k}")
    if not 2 <= nsent(ai.get("summary")) <= 3: errs.append("пересказ не 2-3 предложения")
    if not 1 <= nsent(ai.get("meaning")) <= 2: errs.append("«что значит» не 1-2 предложения")
    if nsent(ai.get("attention")) != 1: errs.append("«во внимание» не одно предложение")
    return errs

def validate(post, c, mock=False):
    errs = []
    if 'href="http' not in post: errs.append("нет ссылки")
    tags = re.findall(r"#\w+", post.split("Источник:")[-1])
    if not tags: errs.append("нет хэштегов")
    bad = [t for t in tags if t not in ALLOWED]
    if bad: errs.append(f"чужие хэштеги {bad}")
    if len(post) > 4000: errs.append("длиннее лимита Telegram")
    if not mock and ("[en→ru]" in post or "[el→ru]" in post): errs.append("заглушка перевода")
    for h in ("Что это значит для вас:", "Что взять во внимание:"):
        if f"<b>{h}</b>" not in post: errs.append(f"нет пункта {h}")
    return errs

def tg(method, payload):
    """Запрос к Telegram с повтором при 429 (сообщение при 429 точно не отправлено), до 15 минут."""
    tok = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    url = f"https://api.telegram.org/bot{tok}/{method}"
    r, deadline = None, time.time() + 15 * 60
    while time.time() < deadline:
        try:
            r = requests.post(url, json=payload, timeout=(15, 120))
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            log(f"Telegram: нет соединения ({type(e).__name__}), повтор через 30с"); r = None; time.sleep(30); continue
        if r.status_code == 429:
            try: wait = int(r.json().get("parameters", {}).get("retry_after", 30))
            except Exception: wait = 30
            log(f"Telegram 429: жду {wait + 5}с"); time.sleep(min(wait + 5, 120)); continue
        break
    if r is None: log("Telegram: не удалось подключиться"); sys.exit(1)
    return r

def main():
    dry = os.environ.get("DRY_RUN", "0") == "1"
    force_url = norm_url(os.environ["FORCE_URL"]) if os.environ.get("FORCE_URL", "").strip() else ""
    del_id = os.environ.get("DELETE_MESSAGE_ID", "").strip()
    now = dt.datetime.now(dt.timezone.utc)
    state_p = HERE / "posted.json"
    state = json.loads(state_p.read_text())
    today = now.astimezone(dt.timezone(dt.timedelta(hours=2))).date().isoformat()
    if not dry and not force_url and any(p["day"] == today for p in state["posted"]) and not os.environ.get("FORCE"):
        log("уже опубликовано сегодня"); return
    history = [p for p in state["posted"] if (now - dt.datetime.fromisoformat(p["at"])).days <= 14 and p["url_n"] != force_url]
    seen_urls = {p["url_n"] for p in state["posted"]} - {force_url}
    key = os.environ.get("DEEPL_API_KEY", "")
    ai_json = os.environ.get("AI_JSON", "").strip()
    list_only = os.environ.get("LIST_ONLY", "0") == "1"
    if ai_json and not force_url: log("ai_json работает только вместе с force_url"); sys.exit(1)
    feeds = json.loads((HERE / "feeds.json").read_text())
    cands = [c for c in candidates(feeds, now, max_age_h=96 if force_url else 72) if c["url_n"] not in seen_urls]
    if force_url:
        cands = [c for c in cands if c["url_n"] == force_url]
        if not cands: log("статья FORCE_URL не найдена в лентах"); sys.exit(1)
    log(f"кандидатов: {len(cands)}")
    pool = cands[:15]
    if not pool: log("нечего публиковать"); sys.exit(0)
    for lang in ("el", "en"):  # заголовки одним запросом на русский: дедуп работает и между языками
        grp = [c for c in pool if c["feed"]["lang"] == lang]
        if grp:
            for c, t in zip(grp, deepl([c["title"] for c in grp], lang, key)): c["title_ru"] = t
    kept, post, chosen, chosen_meta, tries = [], None, None, None, 0
    for c in pool:  # tier A и важные темы первыми, значит при дубле побеждает первоисточник
        tok, nums = tokens(c["title_ru"]), numbers(c["title"])
        d = is_dup(tok, nums, history + kept)
        if d and not force_url:
            log("ДУБЛЬ:", c["feed"]["name"], "|", c["title_ru"], "≈", d.get("title_ru")); continue
        kept.append(dict(tok=sorted(tok), nums=sorted(nums), title_ru=c["title_ru"]))
        if list_only:
            print(json.dumps(dict(title_ru=c["title_ru"], title=c["title"], link=c["link"], source=c["feed"]["name"],
                                  tier=c["feed"]["tier"], tags=c["tags"] + c["place"], pub=c["pub"], text=c["text"][:3000]),
                             ensure_ascii=False))
            tries += 1
            if tries >= 6: break
            continue
        if not ai_json:
            if dry:
                ai = {"summary": "[пересказ]. [второе предложение].", "meaning": "[что значит].", "attention": "[во внимание]."}
            else:
                log("нет ai_json: публикация только через ежедневную задачу Claude"); sys.exit(0)
        else:
            try: ai = json.loads(ai_json)
            except Exception as e: log("ai_json не JSON:", e); sys.exit(1)
        errs = check_ai(ai) if ai_json else []
        if errs: log("ПРОПУСК:", c["title_ru"], "|", errs); continue
        cand_post = build_post(c, c["title_ru"], ai)
        errs = validate(cand_post, c, mock=not key)
        if errs: log("ВАЛИДАЦИЯ НЕ ПРОЙДЕНА:", c["title_ru"], errs); continue
        post, chosen, chosen_meta = cand_post, c, kept[-1]; break
    if list_only: return
    if not post: log("ни одна новость не прошла проверки"); sys.exit(1 if force_url else 0)
    print(post)
    if dry: log("DRY_RUN: не отправляю"); return
    if del_id:
        r = tg("deleteMessage", dict(chat_id=CHAT_ID, message_id=int(del_id)))
        log("удаление сообщения", del_id, ":", r.status_code, r.text[:200])
        if r.ok: state["posted"] = [p for p in state["posted"] if str(p.get("message_id")) != del_id and p["url_n"] != chosen["url_n"]]
    r = tg("sendMessage", dict(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=post, parse_mode="HTML",
                               disable_web_page_preview=True))
    if not r.ok: log("Telegram:", r.status_code, r.text); sys.exit(1)
    state["posted"].append(dict(day=today, at=now.isoformat(), message_id=r.json()["result"]["message_id"],
                                url_n=chosen["url_n"], link=chosen["link"], title_ru=chosen["title_ru"],
                                tok=chosen_meta["tok"], nums=chosen_meta["nums"], source=chosen["feed"]["name"],
                                tags=chosen["tags"] + chosen["place"]))
    state["posted"] = state["posted"][-200:]
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
