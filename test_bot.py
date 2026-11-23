import bot
def t(a): return bot.tokens(a), bot.numbers(a)
def test_dup_cross_source():
    a = "Всеобщая забастовка моряков в Греции 25 ноября"
    b = "24-часовая забастовка моряков в Греции 25 ноября: отмены паромов"
    tok, n = t(a); h = [dict(tok=sorted(t(b)[0]), nums=sorted(t(b)[1]))]
    assert bot.is_dup(tok, n, h)
def test_not_dup():
    a = "Минфин продлил льготы по НДС"; b = "Метро Афин: новые часы работы"
    tok, n = t(a); assert not bot.is_dup(tok, n, [dict(tok=sorted(t(b)[0]), nums=[])])
def test_url_norm():
    assert bot.norm_url("https://www.X.com/a/?utm_source=q#z") == bot.norm_url("https://x.com/a")
def test_validate_rejects():
    c = dict(sents=["a"]*5)
    assert "нет ссылки" in bot.validate("текст\nИсточник: X\n#Греция", c)
    assert any("чужие" in e for e in bot.validate('<a href="http://x">x</a>\nИсточник: x\n#ИИ', c))
    assert "нет хэштегов" in bot.validate('<a href="http://x">x</a>\nИсточник: x', c)

def test_interview_and_quote_titles_rejected():
    import bot
    assert bot.JUNK.search(bot.plain("ΣΥΝΕΝΤΕΥΞΗ ΤΟΥ ΥΠΟΥΡΓΟΥ ΣΤΗΝ ΕΦΗΜΕΡΙΔΑ"))
    assert bot.QUOTE_TITLE.search("Κυριάκος Πιερρακάκης: «Κάθε πρόσθετο πλεόνασμα»")
    assert not bot.QUOTE_TITLE.search("Νέα μέτρα για τα ενοίκια από 1η Ιανουαρίου")
