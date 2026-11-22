"""Shared CSS for the Zariya UI. Injected once from app/ui.py."""

STYLE_BLOCK = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&family=Noto+Nastaliq+Urdu:wght@400;600&display=swap');

:root {
  --bg:       #0d1117;
  --surface:  #161b22;
  --surface2: #1c2128;
  --border:   #21262d;
  --border2:  #30363d;
  --accent:   #58a6ff;
  --accent-d: rgba(88,166,255,0.13);
  --accent-d2:rgba(88,166,255,0.06);
  --user:     #f0883e;
  --user-d:   rgba(240,136,62,0.10);
  --text:     #e6edf3;
  --muted:    #8b949e;
  --success:  #3fb950;
  --danger:   #f85149;
  --warn:     #d29922;
  --purple:   #bc8cff;
  --radius:   12px;
  --font:     'IBM Plex Sans', sans-serif;
  --mono:     'IBM Plex Mono', monospace;
  --urdu:     'Noto Nastaliq Urdu', serif;
}

html, body, [class*="css"] {
  font-family: var(--font) !important;
  background-color: var(--bg) !important;
  color: var(--text) !important;
}

.block-container { padding: 0 !important; }
.main .block-container { padding: 1.5rem 2rem 6rem !important; max-width: 900px; }

section[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 260px !important;
}
section[data-testid="stSidebar"] .block-container { padding: 1rem 0.75rem !important; }
.sidebar-brand { display:flex; align-items:center; gap:10px; padding:0 4px 1rem; border-bottom:1px solid var(--border); margin-bottom:1rem; }
.sidebar-brand .logo { font-size:26px; }
.sidebar-brand .name { font-size:15px; font-weight:600; }
.sidebar-brand .sub  { font-size:11px; color:var(--muted); font-family:var(--urdu); }
.nav-btn { display:flex; align-items:center; gap:8px; padding:8px 10px; border-radius:8px; cursor:pointer; font-size:13px; color:var(--muted); margin-bottom:2px; transition:all .15s; border:1px solid transparent; }
.nav-btn:hover { background:var(--surface2); color:var(--text); }
.nav-btn.active { background:var(--accent-d); color:var(--accent); border-color:rgba(88,166,255,.2); }
.nav-icon { font-size:15px; width:20px; text-align:center; }
.sidebar-section { font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:.7px; padding:8px 4px 4px; }
.sess-row { display:flex; align-items:center; gap:4px; margin-bottom:2px; }
.sess-btn { flex:1; text-align:left; background:transparent; border:1px solid transparent; border-radius:7px; padding:7px 9px; cursor:pointer; font-size:12.5px; color:var(--muted); font-family:var(--font); transition:all .12s; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.sess-btn:hover { background:var(--surface2); color:var(--text); }
.sess-btn.active { background:var(--accent-d); color:var(--accent); border-color:rgba(88,166,255,.18); }
.sess-del { background:transparent; border:none; color:var(--muted); font-size:12px; cursor:pointer; padding:4px 6px; border-radius:5px; }
.sess-del:hover { color:var(--danger); background:rgba(248,81,73,.1); }
.sidebar-stats { font-size:11px; color:var(--muted); line-height:2; padding:8px 4px; border-top:1px solid var(--border); margin-top:8px; }

.page-header { display:flex; align-items:center; gap:14px; padding-bottom:1.2rem; border-bottom:1px solid var(--border); margin-bottom:1.5rem; }
.page-logo { width:42px; height:42px; background:linear-gradient(135deg,#1a2a4a,#0d2137); border:1px solid var(--accent); border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:22px; }
.page-title { font-size:20px; font-weight:600; letter-spacing:-.3px; }
.page-sub { font-size:12px; color:var(--muted); }
.status-pill { margin-left:auto; display:flex; align-items:center; gap:6px; font-size:11px; color:var(--muted); background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:4px 10px; }
.dot { width:7px; height:7px; border-radius:50%; }
.dot.on  { background:var(--success); box-shadow:0 0 5px var(--success); }
.dot.off { background:var(--danger);  box-shadow:0 0 5px var(--danger); }

.msg-wrap { margin-bottom:1rem; }
.msg-row { display:flex; gap:10px; }
.msg-row.user { flex-direction:row-reverse; }
.avatar { width:30px; height:30px; min-width:30px; border-radius:7px; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:600; margin-top:2px; }
.avatar.bot  { background:var(--accent-d); color:var(--accent); border:1px solid rgba(88,166,255,.2); }
.avatar.user { background:var(--user-d);   color:var(--user);   border:1px solid rgba(240,136,62,.2); }
.msg-body { max-width:80%; }
.bubble { padding:11px 15px; border-radius:var(--radius); line-height:1.7; font-size:14px; word-break:break-word; }
.bubble.bot  { background:var(--surface); border:1px solid var(--border); border-top-left-radius:3px; }
.bubble.user { background:var(--user-d);  border:1px solid rgba(240,136,62,.15); border-top-right-radius:3px; }
.bubble p { margin:0 0 .5em; }
.bubble p:last-child { margin:0; }
.bubble pre { background:#0d1117; border:1px solid var(--border); border-radius:7px; padding:12px; overflow-x:auto; margin:.5em 0; }
.bubble code { font-family:var(--mono); font-size:12.5px; }
.bubble :not(pre) > code { background:rgba(13,17,23,.8); padding:2px 6px; border-radius:4px; color:var(--purple); font-size:12.5px; }
.bubble ul, .bubble ol { padding-left:1.4em; margin:.4em 0; }
.bubble li { margin:.2em 0; }
.bubble h1,.bubble h2,.bubble h3 { margin:.6em 0 .3em; font-weight:600; }
.bubble blockquote { border-left:3px solid var(--border2); padding-left:.8em; color:var(--muted); margin:.5em 0; }
.msg-meta { display:flex; gap:8px; align-items:center; margin-top:5px; padding:0 2px; }
.msg-time { font-size:10.5px; color:var(--muted); }
.msg-actions { display:flex; gap:4px; opacity:0; transition:opacity .2s; }
.msg-wrap:hover .msg-actions { opacity:1; }
.action-btn { background:var(--surface); border:1px solid var(--border); border-radius:5px; padding:2px 7px; font-size:11px; color:var(--muted); cursor:pointer; }
.action-btn:hover { color:var(--text); border-color:var(--border2); }

.empty { text-align:center; padding:3.5rem 1rem 2rem; }
.empty-icon { font-size:48px; margin-bottom:1rem; }
.empty-title { font-size:19px; font-weight:600; margin-bottom:.4rem; }
.empty-sub { font-size:14px; color:var(--muted); line-height:1.8; }
.empty-urdu { font-family:var(--urdu); font-size:20px; color:var(--purple); margin:1rem 0; direction:rtl; }
.chips { display:flex; flex-wrap:wrap; gap:7px; justify-content:center; margin-top:1.5rem; }
.chip { background:var(--surface); border:1px solid var(--border); border-radius:18px; padding:6px 13px; font-size:13px; cursor:pointer; }
.chip.urdu { font-family:var(--urdu); direction:rtl; font-size:15px; }

.thinking { display:flex; gap:5px; align-items:center; padding:12px 15px; }
.thinking span { width:7px; height:7px; background:var(--accent); border-radius:50%; animation:bounce .9s ease-in-out infinite; }
.thinking span:nth-child(2) { animation-delay:.2s; }
.thinking span:nth-child(3) { animation-delay:.4s; }
@keyframes bounce { 0%,80%,100%{transform:translateY(0);opacity:.4} 40%{transform:translateY(-6px);opacity:1} }

.fc-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; margin-top:1rem; }
.fc-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px; cursor:pointer; transition:border-color .15s,transform .1s; min-height:120px; display:flex; flex-direction:column; justify-content:center; }
.fc-card:hover { border-color:var(--accent); transform:translateY(-1px); }
.fc-card.flipped { background:var(--accent-d2); border-color:rgba(88,166,255,.3); }
.fc-label { font-size:10px; text-transform:uppercase; letter-spacing:.7px; color:var(--muted); margin-bottom:8px; }
.fc-text { font-size:14px; line-height:1.6; }
.fc-answer { color:var(--accent); }
.fc-progress { display:flex; gap:8px; align-items:center; margin:1rem 0; }
.fc-bar { flex:1; height:4px; background:var(--border); border-radius:2px; overflow:hidden; }
.fc-fill { height:100%; background:var(--accent); border-radius:2px; transition:width .3s; }

.note-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; margin-bottom:10px; cursor:pointer; transition:border-color .12s; }
.note-card:hover { border-color:var(--accent); }
.note-title { font-size:14px; font-weight:500; margin-bottom:4px; }
.note-preview { font-size:12.5px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.note-date { font-size:11px; color:var(--muted); margin-top:6px; }

.setting-group { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px 18px; margin-bottom:12px; }
.setting-title { font-size:13px; font-weight:600; color:var(--text); margin-bottom:12px; display:flex; align-items:center; gap:7px; }
.model-badge { display:inline-flex; align-items:center; gap:6px; background:rgba(63,185,80,.1); border:1px solid rgba(63,185,80,.3); border-radius:20px; padding:4px 12px; font-size:12px; color:var(--success); }
.model-badge.err { background:rgba(248,81,73,.1); border-color:rgba(248,81,73,.3); color:var(--danger); }

div[data-testid="stChatInput"] textarea { font-family:var(--font) !important; font-size:14px !important; }
.stTextInput > div > div { background:var(--surface) !important; border:1px solid var(--border) !important; border-radius:9px !important; }
.stTextInput input { color:var(--text) !important; font-family:var(--font) !important; font-size:14px !important; }
.stTextArea textarea { background:var(--surface) !important; border:1px solid var(--border) !important; color:var(--text) !important; font-family:var(--font) !important; border-radius:9px !important; }
.stButton > button { border-radius:7px !important; font-family:var(--font) !important; font-size:13px !important; }
.stSelectbox > div { background:var(--surface) !important; }
.stSlider > div > div { accent-color:var(--accent) !important; }
div[data-testid="stExpander"] { background:var(--surface); border:1px solid var(--border) !important; border-radius:var(--radius) !important; }
hr { border-color:var(--border) !important; }
.stAlert { border-radius:var(--radius) !important; }
::-webkit-scrollbar { width:5px; height:5px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:var(--border2); border-radius:3px; }
</style>
"""
