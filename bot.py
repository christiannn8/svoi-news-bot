#!/usr/bin/env python3
"""Бот новостей «Свои на юге Афин»: одна новость в день в ветку «Новости».
Правила: см. RULES.md. Перевод только через DeepL, без ИИ-генерации."""
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
 "#закон": r"\blaw\b|\bbill\b|legislat|parliament|ministerial decision|νόμο|νομοσχ|βουλή|υπουργική απόφαση|απόφαση",
 "#аренда": r"\brent\b|rental|tenant|landlord|ενοίκ|μίσθωσ|airbnb|short-term",
 "#недвижимость": r"real estate|propert|housing|mortgage|apartment|ακίνητ|στέγαση|στεγαστικ|κατοικία|spiti mou|σπίτι μου",
 "#документы": r"passport|certificate|document|id card|afm|amka|πιστοποιητ|έγγραφ|ταυτότητα|αφμ|αμκα|gov\.gr",
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
                            sents=sents, tags=tags[:2], place=place, score=score))
    return sorted(out, key=lambda c: -c["score"])

def build_post(c, title_ru, body_ru):
    tags = [t for t in c["tags"] + c["place"] if t in ALLOWED]
    note = " (по данным СМИ)" if c["feed"]["tier"] == "B" and TAXLAW & set(c["tags"]) else ""
    src = f'Источник: <a href="{html.escape(c["link"], quote=True)}">{html.escape(c["feed"]["name"])}</a>{note}'
    return f"📰 <b>{html.escape(title_ru.strip())}</b>\n\n{html.escape(body_ru.strip())}\n\n{src}\n{' '.join(tags)}"

def validate(post, c, mock=False):
    errs = []
    if 'href="http' not in post: errs.append("нет ссылки")
    tags = re.findall(r"#\w+", post.split("Источник:")[-1])
    if not tags: errs.append("нет хэштегов")
    bad = [t for t in tags if t not in ALLOWED]
    if bad: errs.append(f"чужие хэштеги {bad}")
    if len(c["sents"]) < 4: errs.append("меньше 4 предложений")
    if len(post) > 4000: errs.append("длиннее лимита Telegram")
    if not mock and ("[en→ru]" in post or "[el→ru]" in post): errs.append("заглушка перевода")
    return errs

def main():
    dry = os.environ.get("DRY_RUN", "0") == "1"
    now = dt.datetime.now(dt.timezone.utc)
    state_p = HERE / "posted.json"
    state = json.loads(state_p.read_text())
    today = now.astimezone(dt.timezone(dt.timedelta(hours=2))).date().isoformat()
    if not dry and any(p["day"] == today for p in state["posted"]) and not os.environ.get("FORCE"):
        log("уже опубликовано сегодня"); return
    history = [p for p in state["posted"] if (now - dt.datetime.fromisoformat(p["at"])).days <= 14]
    seen_urls = {p["url_n"] for p in state["posted"]}
    key = os.environ.get("DEEPL_API_KEY", "")
    feeds = json.loads((HERE / "feeds.json").read_text())
    cands = [c for c in candidates(feeds, now) if c["url_n"] not in seen_urls]
    log(f"кандидатов: {len(cands)}")
    pool = cands[:15]
    if not pool: log("нечего публиковать"); sys.exit(0)
    # заголовки одним запросом на русский: дедуп работает и между языками
    for lang in ("el", "en"):
        grp = [c for c in pool if c["feed"]["lang"] == lang]
        if grp:
            for c, t in zip(grp, deepl([c["title"] for c in grp], lang, key)): c["title_ru"] = t
    chosen, kept = None, []
    for c in pool:  # уже отсортированы: tier A и важные темы первыми, значит при дубле побеждает первоисточник
        tok, nums = tokens(c["title_ru"]), numbers(c["title"])
        d = is_dup(tok, nums, history + kept)
        if d:
            log("ДУБЛЬ:", c["feed"]["name"], "|", c["title_ru"], "≈", d.get("title_ru")); continue
        kept.append(dict(tok=sorted(tok), nums=sorted(nums), title_ru=c["title_ru"]))
        if chosen is None: chosen = c; chosen_meta = kept[-1]
    if not chosen: log("все кандидаты - дубли"); sys.exit(0)
    body_ru = deepl([" ".join(chosen["sents"])], chosen["feed"]["lang"], key)[0]
    post = build_post(chosen, chosen["title_ru"], body_ru)
    errs = validate(post, chosen, mock=not key)
    if errs: log("ВАЛИДАЦИЯ НЕ ПРОЙДЕНА:", errs); sys.exit(1)
    print(post)
    if dry: log("DRY_RUN: не отправляю"); return
    tok = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    relay = os.environ.get("TG_RELAY")  # запасной путь, если понадобится
    headers = {}
    if relay: url, headers = f"{relay}?method=sendMessage", {"x-bot-token": tok}
    payload = dict(chat_id=CHAT_ID, message_thread_id=THREAD_ID, text=post, parse_mode="HTML",
                   disable_web_page_preview=True)
    r, deadline = None, time.time() + 15 * 60
    while time.time() < deadline:
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=(15, 120))
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            # соединение не установилось: сообщение точно не ушло, повтор безопасен
            log(f"Telegram: нет соединения ({type(e).__name__}), повтор через 30с"); r = None; time.sleep(30); continue
        if r.status_code == 429:
            # лимит Telegram: сообщение не отправлено, ждём и повторяем (до 15 минут)
            try: wait = int(r.json().get("parameters", {}).get("retry_after", 30))
            except Exception: wait = 30
            log(f"Telegram 429: жду {wait + 5}с"); time.sleep(min(wait + 5, 120)); continue
        break
    if r is None: log("Telegram: не удалось подключиться"); sys.exit(1)
    if not r.ok: log("Telegram:", r.status_code, r.text); sys.exit(1)
    state["posted"].append(dict(day=today, at=now.isoformat(), url_n=chosen["url_n"], link=chosen["link"],
                                title_ru=chosen["title_ru"], tok=chosen_meta["tok"], nums=chosen_meta["nums"],
                                source=chosen["feed"]["name"], tags=chosen["tags"] + chosen["place"]))
    state["posted"] = state["posted"][-200:]
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
