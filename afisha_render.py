"""Обложка афиши: фото фона + полупрозрачные плитки событий. Используется afisha.py (GitHub Actions)."""
import base64, pathlib
HERE = pathlib.Path(__file__).parent
FD = HERE / "brand" / "fonts"
def b64(p): return base64.b64encode(pathlib.Path(p).read_bytes()).decode()
def fonts():
    return ''.join(f"@font-face{{font-family:Jost;font-weight:{w};src:url(data:font/woff2;base64,{b64(FD/f'jost-{s}-{w}-normal.woff2')}){';unicode-range:U+0400-04FF' if s=='cyrillic' else ''}}}" for w in (300,400,500,600) for s in ('latin','cyrillic'))
def html(p, bg_path):
    rows = ''.join(f"""<div class=ev><div class=d><b>{e['day']}</b><span>{e['time']}</span></div><div class=tx><div class=n>{e['name']}</div><div class=p>{e['place']}{f"<i>{e['tags']}</i>" if e.get('tags') else ''}</div></div></div>""" for e in p['events'])
    ov = p.get('overlay', 'linear-gradient(180deg,rgba(5,10,30,.5),rgba(5,10,30,.15) 35%,rgba(5,10,30,.55))')
    return f"""<html><head><style>{fonts()}
*{{margin:0;box-sizing:border-box}}
body{{width:1080px;height:1350px;font-family:Jost;color:#fff;position:relative;overflow:hidden;background:#123}}
.bg{{position:absolute;inset:-20px;background:url(data:image/jpeg;base64,{b64(bg_path)}) {p.get('bg_position','center')}/cover}}
.ov{{position:absolute;inset:0;background:{ov}}}
.hd{{position:absolute;left:84px;right:84px;top:92px;display:flex;justify-content:space-between;align-items:flex-end}}
.k{{font-weight:500;font-size:24px;letter-spacing:.32em;opacity:.85}}
.t{{font-weight:300;font-size:118px;letter-spacing:.06em;line-height:1;margin-top:18px}}
.dt{{font-weight:400;font-size:40px;letter-spacing:.04em;padding-bottom:10px}}
.dt b{{display:block;width:56px;height:4px;background:#FF9800;margin:0 0 16px auto;border-radius:2px}}
.list{{position:absolute;left:84px;right:84px;top:400px;display:flex;flex-direction:column;gap:14px}}
.ev{{display:flex;gap:30px;align-items:center;padding:24px 30px;border-radius:24px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.28);backdrop-filter:blur(14px)}}
.d{{width:130px;flex:none}} .d b{{display:block;font-weight:600;font-size:30px;color:#FFB74D}} .d span{{font-size:24px;opacity:.85}}
.n{{font-weight:500;font-size:33px;line-height:1.12}}
.p{{font-size:24px;opacity:.85;margin-top:6px}}
.p i{{font-style:normal;margin-left:14px;padding:2px 12px;border-radius:14px;background:rgba(255,152,0,.9);font-size:20px;font-weight:500}}
.ft{{position:absolute;left:84px;right:84px;bottom:66px;display:flex;justify-content:space-between;align-items:center}}
.wm{{font-weight:500;font-size:46px;letter-spacing:.05em}} .ft span{{font-size:22px;letter-spacing:.24em;opacity:.85}}
</style></head><body><div class=bg></div><div class=ov></div>
<div class=hd><div><div class=k>КУДА ПОЙТИ НА ВЫХОДНЫХ</div><div class=t>Афиша</div></div><div class=dt><b></b>{p['dates']}</div></div>
<div class=list>{rows}</div><div class=ft><div class=wm>SVOI</div><span>СВОИ НА ЮГЕ АФИН</span></div></body></html>"""
def render(p, bg_path, out):
    import asyncio
    from playwright.async_api import async_playwright
    async def go():
        async with async_playwright() as pw:
            b = await pw.chromium.launch(); pg = await b.new_page(viewport={'width':1080,'height':1350})
            await pg.set_content(html(p, bg_path)); await pg.wait_for_timeout(800); await pg.screenshot(path=str(out), type='jpeg', quality=90); await b.close()
    asyncio.run(go())
