(function(){
"use strict";

/* ============ LOCAL UI PREFERENCES (theme/font/etc -- not API keys, those are server-side) ============ */
const LS = {
  get(k, d){ try{ const v = localStorage.getItem(k); return v===null? d : JSON.parse(v); }catch(e){ return d; } },
  set(k, v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} }
};
let uiPrefs = LS.get('zariya_ui_prefs', { theme:'light', fontSize:15, showTimestamps:true, ttsEnabled:false });
let genPrefs = LS.get('zariya_gen_prefs', { persona:'', temperature:0.5 });

let sessions = [];
let notes = [];
let decks = [];
let currentSessionId = null;
let currentNoteId = null;
let currentDeckId = null;
  let activeNoteTagFilter = null;
  let activeDeckTagFilter = null;
let studyQueue = []; let studyIndex = 0; let studyFlipped = false;
let editingIndex = null;
let isGenerating = false;
let stopped = false;
let currentAbort = null;
let serverConfig = { claudeConfigured:false, searchConfigured:false, githubConfigured:false, localModelAvailable:false, localModelStatus:'' };
let me = { signedIn:false };

function uid(){ return Date.now().toString(36) + Math.random().toString(36).slice(2,8); }
function nowISO(){ return new Date().toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}); }
function isUrdu(text){ return /[\u0600-\u06FF]/.test(text||''); }
function escapeHtml(s){ return s.replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function formatInline(s){
  const links = [];
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, text, url)=>{ links.push({text,url}); return '\u0000LINK'+(links.length-1)+'\u0000'; });
  s = escapeHtml(s);
  s = s.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  s = s.replace(/`([^`]+)`/g,'<code>$1</code>');
  s = s.replace(/\n/g,'<br>');
  s = s.replace(/\u0000LINK(\d+)\u0000/g, (m, idx)=>{ const l = links[parseInt(idx,10)]; return '<a href="'+escapeHtml(l.url)+'" target="_blank" rel="noopener noreferrer">'+escapeHtml(l.text)+'</a>'; });
  return s;
}
function renderSearchResultsHtml(query, results){
  // Builds real .search-result/.sr-title/.sr-url/.sr-snippet card markup
  // (see style.css) instead of a markdown-formatted list, so web-search
  // results actually get the card styling those classes were made for.
  const heading = formatInline('**Web search results for "'+query+'"**');
  const cards = results.map(r=>{
    const title = escapeHtml(r.title || r.link || 'Untitled result');
    const url = escapeHtml(r.link || '');
    const snippet = escapeHtml(r.snippet || '');
    return '<div class="search-result">'
      + '<a class="sr-title" href="'+url+'" target="_blank" rel="noopener noreferrer">'+title+'</a>'
      + '<div class="sr-url">'+url+'</div>'
      + '<div class="sr-snippet">'+snippet+'</div>'
      + '</div>';
  }).join('');
  return heading + cards;
}
function renderMarkdown(raw){
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
  let html=''; let lastIndex=0; let m;
  while((m = codeBlockRegex.exec(raw))){
    html += formatInline(raw.slice(lastIndex, m.index));
    const lang = m[1] || 'code'; const code = m[2]; const codeId = 'code_'+uid();
    html += '<div class="code-block"><div class="code-block-head"><span>'+escapeHtml(lang)+'</span><button class="code-copy-btn" data-code-id="'+codeId+'">Copy</button></div><pre><code id="'+codeId+'">'+escapeHtml(code)+'</code></pre></div>';
    lastIndex = codeBlockRegex.lastIndex;
  }
  html += formatInline(raw.slice(lastIndex));
  return html;
}

/* ============ API HELPERS ============ */
async function apiGet(url){
  const r = await fetch(url);
  try{ return await r.json(); }
  catch(e){ throw new Error('Unexpected response from server (status '+r.status+')'); }
}
async function apiPost(url, body, signal){
  const r = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{}), signal });
  try{ return await r.json(); }
  catch(e){ throw new Error('Unexpected response from server (status '+r.status+')'); }
}

async function loadServerState(){
  const [cfg, meRes] = await Promise.all([apiGet('/api/config'), apiGet('/api/me')]);
  serverConfig = cfg; me = meRes;
  const state = cfg.hostedMode ? LS.get('zariya_app_state_v1', {}) : await apiGet('/api/state');
  sessions = Array.isArray(state.sessions) ? state.sessions : [];
  notes = Array.isArray(state.notes) ? state.notes : [];
  decks = Array.isArray(state.decks) ? state.decks : [];
  decks.forEach(d=> (Array.isArray(d.cards) ? d.cards : []).forEach(migrateCardForSpacedRepetition));
  currentSessionId = sessions.length ? sessions[0].id : null;
  const storageDescription = document.getElementById('storageDescription');
  if(storageDescription) storageDescription.textContent = cfg.hostedMode
    ? 'Notes are stored in this browser and are not synced across devices.'
    : 'Notes are stored by this local development server.';
}
let saveTimer;
function saveServerState(){
  clearTimeout(saveTimer);
  if(serverConfig.hostedMode){
    LS.set('zariya_app_state_v1', { sessions, notes, decks });
    return;
  }
  saveTimer = setTimeout(()=>{ apiPost('/api/state', { sessions, notes, decks }).catch(()=>{}); }, 300);
}


/* ============ THEME / UI PREFS ============ */
function applyUiPrefs(){
  document.documentElement.setAttribute('data-theme', uiPrefs.theme);
  document.querySelectorAll('[data-theme-opt]').forEach(el=> el.classList.toggle('active', el.dataset.themeOpt===uiPrefs.theme));
  document.getElementById('fontSizeSlider').value = uiPrefs.fontSize;
  document.getElementById('fontSizeLabel').textContent = uiPrefs.fontSize+'px';
  document.documentElement.style.setProperty('--chat-font-size', uiPrefs.fontSize+'px');
  document.getElementById('toggleTimestamps').classList.toggle('on', uiPrefs.showTimestamps);
  document.getElementById('toggleTTS').classList.toggle('on', uiPrefs.ttsEnabled);
}
function applyGenPrefs(){
  document.getElementById('personaInput').value = genPrefs.persona || '';
  const pct = Math.round((typeof genPrefs.temperature==='number'? genPrefs.temperature : 0.5) * 100);
  document.getElementById('creativitySlider').value = pct;
  updateCreativityLabel(pct);
}
function updateCreativityLabel(pct){
  const label = document.getElementById('creativityLabel');
  const t = pct/100;
  let desc = 'Balanced';
  if(t <= 0.2) desc = 'Focused';
  else if(t <= 0.4) desc = 'Steady';
  else if(t <= 0.6) desc = 'Balanced';
  else if(t <= 0.8) desc = 'Creative';
  else desc = 'Very creative';
  label.textContent = desc+' ('+t.toFixed(2)+')';
}
function updateStatusPill(){
  const dot = document.getElementById('statusDot'); const txt = document.getElementById('statusText');
  if(serverConfig.claudeConfigured){ dot.classList.remove('off'); txt.textContent = 'Claude connected'; }
  else if(serverConfig.hostedMode){ dot.classList.remove('off'); txt.textContent = 'Knowledge mode'; }
  else if(serverConfig.localModelAvailable){ dot.classList.remove('off'); txt.textContent = 'Local model ready'; }
  else if(serverConfig.localModelStatus && /download|loading/i.test(serverConfig.localModelStatus)){ dot.classList.add('off'); txt.textContent = 'Local model starting…'; }
  else { dot.classList.remove('off'); txt.textContent = 'Knowledge mode'; }
}
function updateLocalModelRetryUI(){
  const row = document.getElementById('localModelRetryRow');
  if(!row) return;
  row.style.display = (serverConfig.hostedMode || serverConfig.localModelAvailable) ? 'none' : 'flex';
  const prog = serverConfig.localModelProgress;
  const fill = document.getElementById('localModelProgressFill');
  if(fill){
    const pct = (prog && prog.total) ? Math.round(prog.completed / prog.total * 100) : 0;
    fill.style.width = pct + '%';
  }
}
function renderAccountUI(){
  const sbAvatar = document.getElementById('sbProfileAvatar');
  const sbName = document.getElementById('sbProfileName');
  const signedOutRow = document.getElementById('accountSignedOutRow');
  const signedInRow = document.getElementById('accountSignedInRow');
  const configNote = document.getElementById('githubConfigNote');

  if(me.signedIn){
    sbName.textContent = me.name || me.login;
    sbAvatar.innerHTML = '<img src="'+me.avatar+'" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" alt="">';
    signedOutRow.style.display = 'none';
    signedInRow.style.display = 'flex';
    document.getElementById('accountAvatar').src = me.avatar;
    document.getElementById('accountName').textContent = me.name || me.login;
    document.getElementById('accountBio').textContent = me.bio || '';
  } else {
    sbName.textContent = 'Sign in with GitHub';
    sbAvatar.textContent = 'Z';
    signedOutRow.style.display = 'flex';
    signedInRow.style.display = 'none';
  }
  configNote.textContent = serverConfig.githubConfigured
    ? ''
    : 'GitHub sign-in isn\'t set up on this server yet.';
  document.getElementById('githubSignInBtn').disabled = !serverConfig.githubConfigured;

  document.getElementById('claudeStatusText').textContent = serverConfig.claudeConfigured ? 'Connected' : 'Not configured (optional)';
document.getElementById('localModelStatusText').textContent = serverConfig.hostedMode ? 'Not available in Vercel serverless' : (serverConfig.localModelAvailable ? 'Loaded -- answering your chats' + (serverConfig.localModelName ? ' (' + serverConfig.localModelName + ')' : '') : (serverConfig.localModelStatus || 'Not configured'));
  document.getElementById('searchStatusText').textContent = serverConfig.searchConfigured ? 'Connected' : 'Not configured (optional)';
  const localModelControls = document.getElementById('localModelControls');
  if(localModelControls) localModelControls.style.display = serverConfig.hostedMode ? 'none' : '';
  updateLocalModelRetryUI();
  updateOnboardingBanner();
}
  const ONBOARDING_DISMISS_KEY = 'zariya_onboarding_dismissed';
  function updateOnboardingBanner(){
      const banner = document.getElementById('onboardingBanner');
      if(!banner) return;
      const dismissed = LS.get(ONBOARDING_DISMISS_KEY, false);
      const needsHelp = serverConfig.hostedMode ? !serverConfig.claudeConfigured
        : (!serverConfig.claudeConfigured && !serverConfig.localModelAvailable);
      const copy = banner.querySelector('.ob-text');
      if(copy && serverConfig.hostedMode) copy.textContent =
        'Hosted mode is using Zariya’s built-in Urdu/English knowledge engine. Add a server-side ANTHROPIC_API_KEY to enable generative AI. Chats, notes and flashcards are saved in this browser, not synced to an account.';
      banner.style.display = (needsHelp && !dismissed) ? 'flex' : 'none';
  }
  const onboardingDismissBtn = document.getElementById('onboardingDismissBtn');
  if(onboardingDismissBtn) onboardingDismissBtn.addEventListener('click', ()=>{ LS.set(ONBOARDING_DISMISS_KEY, true); updateOnboardingBanner(); });
document.getElementById('sbProfileRow').addEventListener('click', ()=>switchView('settings'));
document.getElementById('githubSignInBtn').addEventListener('click', ()=>{ window.location.href = '/auth/github/login'; });
document.getElementById('githubSignOutBtn').addEventListener('click', async ()=>{
  await fetch('/auth/logout', { method:'POST' });
  me = { signedIn:false };
  renderAccountUI();
  await loadServerState();
  renderSessionList(); renderChat();
});

/* ============ VIEW SWITCHING ============ */
function switchView(name){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('view-'+name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active', n.dataset.view===name));
  document.getElementById('quickTools').style.display = name==='chat' ? '' : 'none';
  closeSidebarMobile();
  if(name==='notepad') renderNotesList();
  if(name==='flashcards') renderDeckGrid();
if(name==='settings') loadModelList();
}
document.querySelectorAll('.nav-item').forEach(n=> n.addEventListener('click', ()=>switchView(n.dataset.view)));

function openSidebarMobile(){ document.getElementById('sidebar').classList.add('open'); document.getElementById('sbScrim').classList.add('show'); }
function closeSidebarMobile(){ document.getElementById('sidebar').classList.remove('open'); document.getElementById('sbScrim').classList.remove('show'); }
document.getElementById('hamburgerBtn').addEventListener('click', openSidebarMobile);
document.getElementById('sbScrim').addEventListener('click', closeSidebarMobile);

/* ============ SESSIONS ============ */
function newSession(){
  const s = { id:uid(), title:'New chat', messages:[], createdAt:Date.now() };
  sessions.unshift(s); currentSessionId = s.id;
  saveServerState(); renderSessionList(); renderChat();
}
function currentSession(){ return sessions.find(s=>s.id===currentSessionId); }
function deleteSession(id, ev){
  ev.stopPropagation();
  const target = sessions.find(s=>s.id===id);
  if(!confirm('Delete "'+((target&&target.title)||'this chat')+'"? This cannot be undone.')) return;
  sessions = sessions.filter(s=>s.id!==id);
  if(currentSessionId===id) currentSessionId = sessions.length? sessions[0].id : null;
  saveServerState(); renderSessionList(); renderChat();
}
function renderSessionList(){
  const wrap = document.getElementById('sessList');
  const q = document.getElementById('sessSearch').value.trim().toLowerCase();
  wrap.innerHTML = '<div class="sb-sessions-label">Recents</div>';
  const filtered = sessions.filter(s=> !q || s.title.toLowerCase().includes(q) || s.messages.some(m=>m.content.toLowerCase().includes(q)));
  if(!filtered.length) wrap.innerHTML += '<div style="padding:8px 9px;color:var(--text-muted);font-size:12px;">No chats yet</div>';
  filtered.forEach(s=>{
    const div = document.createElement('div');
    div.className = 'sess-item' + (s.id===currentSessionId?' active':'');
    div.innerHTML = '<span class="sess-title">'+escapeHtml(s.title)+'</span><button class="sess-del" title="Delete chat" aria-label="Delete chat"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6"/></svg></button>';
    div.addEventListener('click', ()=>{ currentSessionId = s.id; editingIndex=null; renderSessionList(); renderChat(); closeSidebarMobile(); });
    div.querySelector('.sess-del').addEventListener('click', (e)=>deleteSession(s.id, e));
    wrap.appendChild(div);
  });
}
document.getElementById('sessSearch').addEventListener('input', renderSessionList);
document.getElementById('newChatBtn').addEventListener('click', newSession);


/* ============ CHAT RENDER ============ */
function renderChat(){
  const inner = document.getElementById('chat-inner');
  const scroll = document.getElementById('chat-scroll');
  const session = currentSession();
  inner.innerHTML = '';
  if(!session || !session.messages.length){
    scroll.classList.add('empty-mode'); inner.classList.add('empty-mode');
    const hour = new Date().getHours();
    const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    const hero = document.createElement('div');
    hero.className = 'empty-hero';
    hero.innerHTML = '<h2>'+greeting+'</h2><div class="urdu-line">کچھ بھی پوچھیں</div><p>Ask anything in Urdu or English.</p>';
    inner.appendChild(hero);
    return;
  }
  scroll.classList.remove('empty-mode'); inner.classList.remove('empty-mode');
  session.messages.forEach((m, idx)=>renderBubble(m, idx, idx===session.messages.length-1 && m.role==='assistant'));
  scroll.scrollTop = 999999;
}
function renderBubble(m, idx, isLast){
  const inner = document.getElementById('chat-inner');
  const row = document.createElement('div');
  row.className = 'msg-row ' + (m.role==='user'?'user':'assistant');

  if(m.role==='user' && idx===editingIndex){
    row.innerHTML = '<div class="bubble-col user-col" style="max-width:92%;width:100%;"><textarea class="edit-textarea" id="editTa">'+escapeHtml(m.content)+'</textarea><div class="edit-actions"><button class="btn" id="editCancelBtn">Cancel</button><button class="btn primary" id="editSaveBtn">Save &amp; submit</button></div></div>';
    inner.appendChild(row);
    const ta = row.querySelector('#editTa');
    ta.addEventListener('input', ()=>{ ta.style.height='auto'; ta.style.height=ta.scrollHeight+'px'; });
    setTimeout(()=>{ ta.focus(); ta.style.height='auto'; ta.style.height=ta.scrollHeight+'px'; },0);
    row.querySelector('#editCancelBtn').addEventListener('click', ()=>{ editingIndex=null; renderChat(); });
    row.querySelector('#editSaveBtn').addEventListener('click', ()=>saveEdit(idx));
    return;
  }

  const urduClass = isUrdu(m.content) ? 'is-urdu' : '';
  if(m.role==='user'){
    row.innerHTML = '<div class="bubble-col user-col"><div class="bubble user '+urduClass+'">'+formatInline(m.content)+'</div>'+
      (uiPrefs.showTimestamps ? '<div class="msg-meta">'+(m.ts||'')+'</div>' : '')+
      '<div class="msg-actions"><button class="ghost-btn" data-act="edit">Edit</button></div></div>';
    row.querySelector('[data-act="edit"]').addEventListener('click', ()=>{ editingIndex=idx; renderChat(); });
  } else {
    row.innerHTML = '<img class="avatar-logo" src="/static/logo.png" alt=""><div class="bubble-col assistant-col"><div class="bubble assistant '+urduClass+'">'+(m.html || renderMarkdown(m.content))+'</div>'+
      (uiPrefs.showTimestamps ? '<div class="msg-meta">'+(m.ts||'')+'</div>' : '')+
      '<div class="msg-actions"><button class="ghost-btn" data-act="copy">Copy</button><button class="ghost-btn" data-act="speak">Read aloud</button><button class="ghost-btn" data-act="up" title="Good answer">Helpful</button><button class="ghost-btn" data-act="down" title="Not helpful">Not helpful</button>'+
      (isLast?'<button class="ghost-btn" data-act="regen">Regenerate</button>':'')+'</div></div>';
    row.querySelector('[data-act="copy"]').addEventListener('click', ()=>{ navigator.clipboard && navigator.clipboard.writeText(m.content); });
    row.querySelector('[data-act="speak"]').addEventListener('click', ()=>speak(m.content));
    const regen = row.querySelector('[data-act="regen"]');
    if(regen) regen.addEventListener('click', regenerateLast);
    const upBtn = row.querySelector('[data-act="up"]');
    if(upBtn) upBtn.addEventListener('click', ()=>sendFeedback(idx, 'up', upBtn));
    const downBtn = row.querySelector('[data-act="down"]');
    if(downBtn) downBtn.addEventListener('click', ()=>sendFeedback(idx, 'down', downBtn));
    row.querySelectorAll('.code-copy-btn').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const codeEl = document.getElementById(btn.dataset.codeId);
        if(codeEl && navigator.clipboard){ navigator.clipboard.writeText(codeEl.textContent); const old=btn.textContent; btn.textContent='Copied'; setTimeout(()=>btn.textContent=old,1200); }
      });
    });
  }
  inner.appendChild(row);
}
function sendFeedback(idx, rating, btn){
  const session = currentSession(); if(!session) return;
  const userMsg = session.messages[idx-1];
  if(!userMsg || userMsg.role!=='user') return;
  apiPost('/api/feedback', { question: userMsg.content, rating });
  const row = btn.closest('.msg-actions');
  if(row){ row.querySelectorAll('[data-act="up"],[data-act="down"]').forEach(b=>b.disabled=true); }
  btn.classList.add('active');
  btn.textContent = rating==='up' ? 'Thanks!' : 'Noted';
}
function saveEdit(idx){
    if(isGenerating) return;
  const ta = document.getElementById('editTa');
  const newText = ta.value.trim(); if(!newText) return;
  const session = currentSession();
  session.messages[idx].content = newText;
  session.messages = session.messages.slice(0, idx+1);
  editingIndex = null;
  saveServerState(); renderChat();
  respondTo(session);
}


/* ============ SEND / RESPOND ============ */
const input = document.getElementById('chat-input');
const sendBtn = document.getElementById('sendBtn');
const SEND_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
const STOP_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>';
function syncSendState(){ if(isGenerating) return; sendBtn.disabled = input.value.trim().length===0; }
input.addEventListener('input', ()=>{ input.style.height='auto'; input.style.height=Math.min(input.scrollHeight,160)+'px'; syncSendState(); });
input.addEventListener('keydown', (e)=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); if(!sendBtn.disabled) sendMessage(); } });
sendBtn.addEventListener('click', ()=>{ if(sendBtn.dataset.mode==='stop'){ stopGenerating(); } else if(!sendBtn.disabled){ sendMessage(); } });
syncSendState();

function sendMessage(){
  const text = input.value.trim(); if(!text) return;
  if(!currentSession()) newSession();
  const session = currentSession();
  session.messages.push({ role:'user', content:text, ts:nowISO() });
  if(session.title==='New chat') session.title = text.slice(0,40);
  saveServerState(); renderSessionList(); renderChat();
  input.value=''; input.style.height='auto'; syncSendState();
  respondTo(session);
}
function setGenerating(on){
  isGenerating = on;
  if(on){ sendBtn.dataset.mode='stop'; sendBtn.innerHTML=STOP_ICON; sendBtn.disabled=false; }
  else { sendBtn.dataset.mode='send'; sendBtn.innerHTML=SEND_ICON; syncSendState(); }
}
function showThinking(){
  const inner = document.getElementById('chat-inner');
  const row = document.createElement('div');
  row.className='msg-row assistant'; row.id='thinkingRow';
  row.innerHTML = '<div class="thinking-row"><img class="thinking-logo" src="/static/logo.png" alt=""><span class="thinking-label">Thinking…</span></div>';
  inner.appendChild(row);
  document.getElementById('chat-scroll').scrollTop = 999999;
}
function removeThinking(){ const r=document.getElementById('thinkingRow'); if(r) r.remove(); }

async function respondTo(session){
  stopped = false; setGenerating(true); showThinking();
  currentAbort = new AbortController();
  let reply = '';
  let bubbleEl = null;
  try{
    const res = await fetch('/api/chat/stream', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
body: JSON.stringify({ messages: session.messages.map(m=>({role:m.role, content:m.content})), systemPrompt: genPrefs.persona || undefined, temperature: typeof genPrefs.temperature==='number' ? genPrefs.temperature : undefined }),
      signal: currentAbort.signal
    });
    if(!res.ok || !res.body){
      let data = {}; try{ data = await res.json(); }catch(e){}
      reply = data.error || 'Something went wrong.';
    } else {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while(true){
        const {done, value} = await reader.read();
        if(done) break;
        buf += decoder.decode(value, {stream:true});
        let idx;
        while((idx = buf.indexOf('\n\n')) !== -1){
          const chunk = buf.slice(0, idx); buf = buf.slice(idx+2);
          const line = chunk.split('\n').find(l=>l.startsWith('data: '));
          if(!line) continue;
          let payload;
          try{ payload = JSON.parse(line.slice(6)); }catch(e){ continue; }
          if(payload.delta){
            reply += payload.delta;
            if(!bubbleEl){ removeThinking(); bubbleEl = appendStreamingBubble(); }
            updateStreamingBubble(bubbleEl, reply);
          }
        }
      }
    }
  }catch(err){
    if(err.name==='AbortError'){ removeThinking(); setGenerating(false); return; }
    reply = 'Could not reach the server: ' + (err.message||'unknown error');
  }
  removeThinking(); setGenerating(false);
  if(stopped) return;
  if(!reply) reply = 'Something went wrong.';
  session.messages.push({ role:'assistant', content:reply, ts:nowISO() });
  saveServerState(); renderChat();
  if(uiPrefs.ttsEnabled) speak(reply);
}
function appendStreamingBubble(){
  const inner = document.getElementById('chat-inner');
  const scroll = document.getElementById('chat-scroll');
  scroll.classList.remove('empty-mode'); inner.classList.remove('empty-mode');
  const row = document.createElement('div');
  row.className = 'msg-row assistant';
  row.innerHTML = '<img class="avatar-logo" src="/static/logo.png" alt=""><div class="bubble-col assistant-col"><div class="bubble assistant" id="streamingBubbleContent"></div></div>';
  inner.appendChild(row);
  scroll.scrollTop = 999999;
  return row.querySelector('#streamingBubbleContent');
}
function updateStreamingBubble(el, text){
  el.innerHTML = renderMarkdown(text);
  el.classList.toggle('is-urdu', isUrdu(text));
  document.getElementById('chat-scroll').scrollTop = 999999;
}
function stopGenerating(){ stopped = true; if(currentAbort) currentAbort.abort(); removeThinking(); setGenerating(false); }
function regenerateLast(){
    if(isGenerating) return;
  const session = currentSession(); if(!session) return;
  const lastAssistantIdx = [...session.messages].reverse().findIndex(m=>m.role==='assistant');
  if(lastAssistantIdx===-1) return;
  session.messages.splice(session.messages.length-1-lastAssistantIdx, 1);
  saveServerState(); renderChat(); respondTo(session);
}

/* ============ QUICK TOOLS ============ */
document.querySelectorAll('.qt-btn').forEach(btn=> btn.addEventListener('click', ()=>runQuickTool(btn.dataset.tool)));
async function runQuickTool(tool){
    if(isGenerating) return;
  const session = currentSession(); if(!session || !session.messages.length) return;
  const payload = { messages: session.messages.map(m=>({role:m.role, content:m.content})) };
  if(tool==='summarize'){
    const {result} = await apiPost('/api/tools/summarize', payload);
    session.messages.push({role:'assistant', content:'**Conversation summary**\n\n'+result, ts:nowISO()});
  } else if(tool==='keypoints'){
    const {result} = await apiPost('/api/tools/keypoints', payload);
    session.messages.push({role:'assistant', content:'**Key points**\n\n'+result, ts:nowISO()});
  } else if(tool==='translate'){
    const {result} = await apiPost('/api/tools/translate', payload);
    session.messages.push({role:'assistant', content:'**Rough translation**\n\n'+result, ts:nowISO()});
  } else if(tool==='flashcards'){
    const {cards} = await apiPost('/api/tools/flashcards', payload);
    if(cards && cards.length){
      const deck = {id:uid(), name:session.title+' - flashcards', tags:[], cards: cards.map(c=>({id:uid(), front:c.front, back:c.back, known:false})), createdAt:Date.now()};
      decks.unshift(deck); saveServerState();
      switchView('flashcards'); renderDeckGrid(); openDeck(deck.id);
      return;
    }
    session.messages.push({role:'assistant', content:'Not enough content yet to build flashcards.', ts:nowISO()});
  } else if(tool==='websearch'){
    const lastUser = [...session.messages].reverse().find(m=>m.role==='user');
    if(!lastUser) return;
    showThinking();
    const res = await apiPost('/api/search', { query: lastUser.content });
    removeThinking();
    if(res.error){
      session.messages.push({role:'assistant', content: res.error, ts:nowISO()});
    } else if(!res.results || !res.results.length){
      session.messages.push({role:'assistant', content:'No web results came back for that search.', ts:nowISO()});
    } else {
      // content stays plain markdown/text (used by Copy/Read-aloud and export);
      // html holds the rendered .search-result card markup renderBubble()
      // displays instead, once it's available in a persisted session.
      const body = res.results.map((r,i)=> (i+1)+'. '+r.title+'\n'+r.link+'\n'+r.snippet).join('\n\n');
      session.messages.push({
        role:'assistant',
        content:'Web search results for "'+lastUser.content+'":\n\n'+body,
        html: renderSearchResultsHtml(lastUser.content, res.results),
        ts:nowISO(),
      });
    }
  } else if(tool==='title'){
    session.title = session.messages[0].content.slice(0,42);
    saveServerState(); renderSessionList();
    return;
  } else if(tool==='exportchat'){
    const lines = session.messages.map(m=> (m.role==='user' ? '**You:** ' : '**Zariya:** ') + m.content);
    const filename = (session.title||'chat').replace(/[^\w\- ]/g,'').trim().replace(/\s+/g,'_') + '.md';
    downloadFile(filename, '# '+session.title+'\n\n'+lines.join('\n\n'));
    return;
  }
  saveServerState(); renderChat();
}

/* ============ SPEECH ============ */
function speak(text){
  if(!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.replace(/\*\*/g,'').replace(/`/g,''));
  u.lang = isUrdu(text) ? 'ur-PK' : 'en-US';
  const voices = window.speechSynthesis.getVoices();
  const match = voices.find(v=>v.lang===u.lang) || voices.find(v=>v.lang.startsWith(u.lang.slice(0,2)));
  if(match) u.voice = match;
  window.speechSynthesis.speak(u);
}
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognizer=null, listening=false;
const micBtn = document.getElementById('micBtn');
const composerHint = document.getElementById('composerHint');
const composerBox = document.getElementById('composerBox');
const defaultHint = composerHint.textContent;
try{
  if(!SR){
    micBtn.style.opacity='0.35'; micBtn.title='Voice input needs Chrome or Edge on desktop.';
    micBtn.addEventListener('click', ()=>{ composerHint.textContent='Voice input isn\'t supported in this browser.'; setTimeout(()=>composerHint.textContent=defaultHint, 4000); });
  } else if(!window.isSecureContext){
    micBtn.addEventListener('click', ()=>{ composerHint.textContent='Voice input needs https or localhost.'; setTimeout(()=>composerHint.textContent=defaultHint, 4000); });
  } else {
    recognizer = new SR(); recognizer.continuous=false; recognizer.interimResults=true;
    recognizer.onresult = (e)=>{
      let t=''; for(let i=0;i<e.results.length;i++) t+=e.results[i][0].transcript;
      const base = recognizer._base||''; input.value = (base?base+' ':'')+t;
      input.style.height='auto'; input.style.height=Math.min(input.scrollHeight,160)+'px'; syncSendState();
    };
    recognizer.onstart = ()=>{ listening=true; micBtn.classList.add('active'); composerBox.classList.add('listening'); recognizer._base=input.value.trim(); composerHint.textContent='Listening…'; };
    recognizer.onend = ()=>{ listening=false; micBtn.classList.remove('active'); composerBox.classList.remove('listening'); composerHint.textContent=defaultHint; input.focus(); };
    recognizer.onerror = ()=>{ listening=false; micBtn.classList.remove('active'); composerBox.classList.remove('listening'); composerHint.textContent=defaultHint; };
    micBtn.addEventListener('click', ()=>{
      if(listening){ try{recognizer.stop();}catch(e){} return; }
      try{ recognizer.lang = isUrdu(input.value) ? 'ur-PK':'en-US'; recognizer.start(); }catch(e){}
    });
  }
}catch(e){ micBtn.style.opacity='0.35'; }


/* ============ NOTEPAD ============ */
function renderNotesList(){
  const wrap = document.getElementById('notesList'); wrap.innerHTML='';
    renderNoteTagFilterRow();
    const visibleNotes = activeNoteTagFilter ? notes.filter(n=>(n.tags||[]).includes(activeNoteTagFilter)) : notes;
  if(!visibleNotes.length) wrap.innerHTML = '<div class="empty-mini"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg><span>No notes yet</span></div>';
  visibleNotes.forEach(n=>{
    const div = document.createElement('div');
    div.className = 'note-card'+(n.id===currentNoteId?' active':'');
    div.innerHTML = '<div class="note-card-title">'+escapeHtml(n.title||'Untitled')+'</div><div class="note-card-preview">'+escapeHtml((n.body||'').slice(0,60))+'</div>'+((n.tags&&n.tags.length)?'<div class="note-card-tags">'+n.tags.map(t=>'<span>'+escapeHtml(t)+'</span>').join('')+'</div>':'');
    div.addEventListener('click', ()=>openNote(n.id));
    wrap.appendChild(div);
  });
  if(!currentNoteId && notes.length) openNote(notes[0].id);
  if(!notes.length){ document.getElementById('note-title-input').value=''; document.getElementById('note-body-input').value=''; }
}
  function renderNoteTagFilterRow(){
      const row = document.getElementById('noteTagFilterRow');
      if(!row) return;
      const tagCounts = {};
      notes.forEach(n=>(n.tags||[]).forEach(t=>{ tagCounts[t] = (tagCounts[t]||0)+1; }));
      const tags = Object.keys(tagCounts).sort();
      if(!tags.length){ row.innerHTML = ''; return; }
      row.innerHTML = tags.map(t=>'<span class="tag-chip'+(activeNoteTagFilter===t?' active':'')+'" data-tag="'+escapeHtml(t)+'">'+escapeHtml(t)+' ('+tagCounts[t]+')</span>').join('');
      row.querySelectorAll('.tag-chip').forEach(chip=>{
            chip.addEventListener('click', ()=>{
                    const t = chip.dataset.tag;
                    activeNoteTagFilter = activeNoteTagFilter===t ? null : t;
                    renderNotesList();
            });
      });
  }
function openNote(id){
  currentNoteId = id;
  const n = notes.find(n=>n.id===id);
  document.getElementById('note-title-input').value = n? n.title : '';
  document.getElementById('note-body-input').value = n? n.body : '';
  document.getElementById('note-tags-input').value = n && n.tags ? n.tags.join(', ') : '';  
  renderNotesList();
}
document.getElementById('newNoteBtn').addEventListener('click', ()=>{
  const n = {id:uid(), title:'Untitled note', body:'', tags:[], updatedAt:Date.now()};
  notes.unshift(n); currentNoteId=n.id; saveServerState(); renderNotesList();
  document.getElementById('note-title-input').focus();
});
document.getElementById('deleteNoteBtn').addEventListener('click', ()=>{
  if(!currentNoteId) return;
  const n = notes.find(n=>n.id===currentNoteId);
  if(!confirm('Delete "'+((n&&n.title)||'this note')+'"? This cannot be undone.')) return;
  notes = notes.filter(n=>n.id!==currentNoteId);
  currentNoteId = notes.length? notes[0].id : null;
  saveServerState(); renderNotesList();
});
let noteTitleSaveTimer, noteBodySaveTimer;
document.getElementById('note-title-input').addEventListener('input', ()=>{
  clearTimeout(noteTitleSaveTimer);
  noteTitleSaveTimer = setTimeout(()=>{ const n=notes.find(n=>n.id===currentNoteId); if(n){ n.title=document.getElementById('note-title-input').value||'Untitled note'; saveServerState(); renderNotesList(); } }, 400);
});
document.getElementById('note-body-input').addEventListener('input', ()=>{
  clearTimeout(noteBodySaveTimer);
  noteBodySaveTimer = setTimeout(()=>{ const n=notes.find(n=>n.id===currentNoteId); if(n){ n.body=document.getElementById('note-body-input').value; saveServerState(); renderNotesList(); } }, 400);
});
document.getElementById('exportNoteBtn').addEventListener('click', ()=>{
  const n = notes.find(n=>n.id===currentNoteId); if(!n) return;
  downloadFile((n.title||'note')+'.md', '# '+n.title+'\n\n'+n.body);
});
  let noteTagsSaveTimer;
  document.getElementById('note-tags-input').addEventListener('input', ()=>{
      clearTimeout(noteTagsSaveTimer);
      noteTagsSaveTimer = setTimeout(()=>{
            const n = notes.find(n=>n.id===currentNoteId);
            if(n){
                    n.tags = document.getElementById('note-tags-input').value.split(',').map(t=>t.trim().toLowerCase()).filter(Boolean);
                    saveServerState(); renderNotesList();
            }
      }, 400);
  });
function buildCardsFromNoteText(text){
  const lines = text.split('\n').map(l=>l.trim()).filter(Boolean);

  const qaCards = [];
  for(let i=0;i<lines.length-1;i++){
    const qm = lines[i].match(/^q(?:uestion)?\s*[:.\-]\s*(.+)$/i);
    const am = lines[i+1].match(/^a(?:nswer)?\s*[:.\-]\s*(.+)$/i);
    if(qm && am){ qaCards.push({front:qm[1].trim(), back:am[1].trim()}); i++; }
  }
  if(qaCards.length) return qaCards;

  const glossaryCards = [];
  const sepRe = /^(.{2,80}?)\s*[:—–]\s+(.{2,300})$/;
  for(const raw of lines){
    const line = raw.replace(/^[-*•\d.]+\s*/, '');
    const m = line.match(sepRe);
    if(m && !/^https?:\/\//i.test(m[2]) && !/^\/\//.test(m[1])){
      glossaryCards.push({front:m[1].trim(), back:m[2].trim()});
    }
  }
  if(glossaryCards.length) return glossaryCards;

  if(lines.length >= 2 && lines.length % 2 === 0){
    let looksAlternating = true;
    for(let i=0;i<lines.length;i+=2){
      const prompt = lines[i];
      if(prompt.length > 120 && !/\?\s*$/.test(prompt)){ looksAlternating = false; break; }
    }
    if(looksAlternating){
      const fallbackCards = [];
      for(let i=0;i<lines.length-1;i+=2) fallbackCards.push({front:lines[i], back:lines[i+1]});
      return fallbackCards;
    }
  }
  return [];
}
document.getElementById('noteToFlashBtn').addEventListener('click', ()=>{
  const n = notes.find(n=>n.id===currentNoteId);
  if(!n || !n.body.trim()) return;
  const cards = buildCardsFromNoteText(n.body).map(c=>migrateCardForSpacedRepetition({id:uid(), front:c.front, back:c.back, known:false}));
  if(cards.length){
    const deck = {id:uid(), name:n.title+' - flashcards', tags:(n.tags||[]).slice(), cards, createdAt:Date.now()};
    decks.unshift(deck); saveServerState();
    switchView('flashcards'); renderDeckGrid(); openDeck(deck.id);
  } else {
    alert('Couldn\'t find clear question/answer or term/definition pairs in this note.\n\nTry formatting lines as "Q: ..." / "A: ..." pairs, or "Term: definition" lines, and try again.');
  }
});

let quizQueue = [], quizIndex = 0, quizScore = 0, quizAnswered = false;
let reviewingAllCards = false;

/* ============ SPACED REPETITION (SM-2) ============ */
function migrateCardForSpacedRepetition(c){
  if(c.due === undefined) c.due = new Date(0).toISOString();
  if(c.ease === undefined) c.ease = 2.5;
  if(c.interval === undefined) c.interval = 0;
  if(c.reps === undefined) c.reps = 0;
  return c;
}
function sm2Grade(card, quality){
  card.reps = card.reps || 0;
  card.ease = card.ease || 2.5;
  card.interval = card.interval || 0;
  if(quality < 3){
    card.reps = 0;
    card.interval = 1;
  } else {
    card.reps += 1;
    if(card.reps === 1) card.interval = 1;
    else if(card.reps === 2) card.interval = 6;
    else card.interval = Math.round(card.interval * card.ease);
    card.ease = Math.max(1.3, card.ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)));
  }
  const due = new Date();
  due.setDate(due.getDate() + card.interval);
  card.due = due.toISOString();
  card.known = quality >= 3;
  return card;
}
function cardsDue(cards){ return cards.filter(c=> new Date(c.due||0) <= new Date()); }


/* ============ FLASHCARDS ============ */
function renderDeckGrid(){
  document.getElementById('studyArea').style.display='none';
  document.getElementById('quizArea').style.display='none';
  const grid = document.getElementById('deckGrid'); grid.style.display='grid'; grid.innerHTML='';
    decks.forEach(d=>{ if(!d.tags) d.tags = []; });
    renderDeckTagFilterRow();
    const visibleDecks = activeDeckTagFilter ? decks.filter(d=>(d.tags||[]).includes(activeDeckTagFilter)) : decks;
  if(!visibleDecks.length){ grid.innerHTML='<div class="empty-mini" style="grid-column:1/-1;"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="6" width="16" height="12" rx="2"/><path d="M6 2h16v12"/></svg><span>No decks yet -- chat, then use "Make flashcards" above the message box</span></div>'; return; }
  visibleDecks.forEach(d=>{
    d.cards.forEach(migrateCardForSpacedRepetition);
    const known = d.cards.filter(c=>c.known).length;
    const pct = d.cards.length? Math.round(known/d.cards.length*100):0;
    const due = cardsDue(d.cards).length;
    const card = document.createElement('div'); card.className='deck-card';
    card.innerHTML = '<h3>'+escapeHtml(d.name)+'</h3><p>'+d.cards.length+' card'+(d.cards.length!==1?'s':'')+' · '+pct+'% known'+(due? ' · <strong style="color:var(--accent-strong);">'+due+' due</strong>':' · none due')+'</p><div class="deck-progress"><div class="deck-progress-fill" style="width:'+pct+'%"></div></div>'+
        '<div class="deck-card-tags">'+((d.tags&&d.tags.length)?d.tags.map(t=>'<span>'+escapeHtml(t)+'</span>').join(''):'')+'</div>'+
      '<div class="deck-card-actions"><button class="deck-action-btn" data-action="study">Study</button><button class="deck-action-btn" data-action="quiz"'+(d.cards.length<2?' disabled title="Needs at least 2 cards"':'')+'>Quiz</button><button class="deck-action-btn" data-action="rename" title="Rename deck" aria-label="Rename deck">Rename</button><button class="deck-action-btn" data-action="export" title="Download as JSON">Export</button><button class="deck-action-btn danger" data-action="delete" title="Delete deck" aria-label="Delete deck">Delete</button></div>';
    card.querySelector('[data-action="study"]').addEventListener('click', (e)=>{ e.stopPropagation(); openDeck(d.id); });
    const quizBtn = card.querySelector('[data-action="quiz"]');
    quizBtn.addEventListener('click', (e)=>{ e.stopPropagation(); if(!quizBtn.disabled) startQuiz(d.id); });
    card.querySelector('[data-action="export"]').addEventListener('click', (e)=>{ e.stopPropagation(); exportDeck(d); });
    card.querySelector('[data-action="rename"]').addEventListener('click', (e)=>{ e.stopPropagation(); renameDeck(d.id); });
    card.querySelector('[data-action="delete"]').addEventListener('click', (e)=>{ e.stopPropagation(); deleteDeck(d.id); });
    card.addEventListener('click', ()=>openDeck(d.id));
    grid.appendChild(card);
  });
}
function renameDeck(id){
  const deck = decks.find(d=>d.id===id); if(!deck) return;
  const name = prompt('Rename deck', deck.name);
  if(name===null) return;
  const trimmed = name.trim();
  if(!trimmed) return;
  deck.name = trimmed;
  saveServerState(); renderDeckGrid();
}
function deleteDeck(id){
  const deck = decks.find(d=>d.id===id); if(!deck) return;
  if(!confirm('Delete deck "'+deck.name+'"? This cannot be undone.')) return;
  decks = decks.filter(d=>d.id!==id);
  if(currentDeckId===id) currentDeckId = null;
  saveServerState(); renderDeckGrid();
}
function exportDeck(deck){
  const payload = { zariyaDeckExport: 1, name: deck.name, tags: deck.tags||[], cards: deck.cards.map(c=>({
    front: c.front, back: c.back, known: !!c.known, ease: c.ease, interval: c.interval, reps: c.reps, due: c.due
  })) };
  downloadFile(deck.name.replace(/[^\w\- ]/g, '').trim().replace(/\s+/g, '_') + '.json', JSON.stringify(payload, null, 2));
}
function importDeckFromJson(text){
  let parsed;
  try { parsed = JSON.parse(text); } catch(e){ alert('That file is not valid JSON.'); return; }
  const cardsSource = Array.isArray(parsed) ? parsed : parsed.cards;
  const name = Array.isArray(parsed) ? 'Imported deck' : (parsed.name || 'Imported deck');
  if(!Array.isArray(cardsSource) || !cardsSource.length){ alert('No cards found in that file.'); return; }
  const cards = [];
  for(const c of cardsSource){
    if(!c || typeof c.front !== 'string' || typeof c.back !== 'string') continue;
    cards.push(migrateCardForSpacedRepetition({
      id: uid(), front: c.front, back: c.back, known: !!c.known,
      ease: typeof c.ease === 'number' ? c.ease : undefined,
      interval: typeof c.interval === 'number' ? c.interval : undefined,
      reps: typeof c.reps === 'number' ? c.reps : undefined,
      due: typeof c.due === 'string' ? c.due : undefined
    }));
  }
  if(!cards.length){ alert('No valid cards (each needs a front and back) found in that file.'); return; }
  const tags = Array.isArray(parsed) ? [] : (Array.isArray(parsed.tags) ? parsed.tags : []);
  decks.unshift({ id: uid(), name, tags, cards, createdAt: Date.now() });
  saveServerState(); renderDeckGrid();
}
document.getElementById('importDeckBtn').addEventListener('click', ()=>document.getElementById('importDeckFile').click());
document.getElementById('importDeckFile').addEventListener('change', (e)=>{
  const file = e.target.files[0]; if(!file) return;
  const reader = new FileReader();
  reader.onload = ()=>importDeckFromJson(reader.result);
  reader.readAsText(file);
  e.target.value = '';
});
function openDeck(id){
  currentDeckId = id;
  const deck = decks.find(d=>d.id===id); if(!deck || !deck.cards.length) return;
  deck.cards.forEach(migrateCardForSpacedRepetition);
  reviewingAllCards = false;
  studyQueue = cardsDue(deck.cards); studyIndex=0; studyFlipped=false;
  document.getElementById('deckGrid').style.display='none';
  document.getElementById('studyArea').style.display='block';
  renderStudy();
}
function renderStudy(){
  const area = document.getElementById('studyArea');
  const deck = decks.find(d=>d.id===currentDeckId);
  if(!reviewingAllCards && !studyQueue.length){
    area.innerHTML = '<h2 style="font-weight:700;">All caught up</h2><p style="color:var(--text-muted);margin-bottom:18px;">No cards due for review in '+escapeHtml(deck.name)+' right now.</p>'+
      '<div class="study-controls"><button class="sc-btn" id="reviewAllBtn">Review all cards anyway</button><button class="btn primary" id="backToDecks">Back to decks</button></div>';
    document.getElementById('reviewAllBtn').addEventListener('click', ()=>{ reviewingAllCards=true; studyQueue=deck.cards.slice(); studyIndex=0; studyFlipped=false; renderStudy(); });
    document.getElementById('backToDecks').addEventListener('click', renderDeckGrid);
    return;
  }
  if(studyIndex >= studyQueue.length){
    area.innerHTML = '<h2 style="font-weight:700;">Deck complete</h2><p style="color:var(--text-muted);margin-bottom:18px;">You reviewed '+studyQueue.length+' card'+(studyQueue.length!==1?'s':'')+'.</p><button class="btn primary" id="backToDecks">Back to decks</button>';
    document.getElementById('backToDecks').addEventListener('click', renderDeckGrid);
    saveServerState(); return;
  }
  const c = studyQueue[studyIndex];
  area.innerHTML = '<div class="study-progress-text">Card '+(studyIndex+1)+' of '+studyQueue.length+' -- '+escapeHtml(deck.name)+'</div>'+
    '<div class="card-flip-zone"><div class="flip-card '+(studyFlipped?'flipped':'')+'" id="flipCard">'+
    '<div class="flip-face front '+(isUrdu(c.front)?'is-urdu urdu':'')+'">'+escapeHtml(c.front)+'</div>'+
    '<div class="flip-face back '+(isUrdu(c.back)?'is-urdu urdu':'')+'">'+escapeHtml(c.back)+'</div></div></div>'+
    (studyFlipped
      ? '<div class="study-controls"><button class="sc-btn again" data-q="0">Again</button><button class="sc-btn" data-q="3">Hard</button><button class="sc-btn known" data-q="4">Good</button><button class="sc-btn known" data-q="5">Easy</button></div>'
      : '<div class="study-controls"><button class="sc-btn" id="scFlip">Flip to grade</button></div>');
  document.getElementById('flipCard').addEventListener('click', ()=>{ studyFlipped=!studyFlipped; renderStudy(); });
  if(!studyFlipped){
    document.getElementById('scFlip').addEventListener('click', (e)=>{ e.stopPropagation(); studyFlipped=true; renderStudy(); });
  } else {
    area.querySelectorAll('[data-q]').forEach(btn=>{
      btn.addEventListener('click', (e)=>{
        e.stopPropagation();
        const quality = parseInt(btn.dataset.q, 10);
        const rc = deck.cards.find(x=>x.id===c.id) || c;
        sm2Grade(rc, quality);
        if(quality < 3) studyQueue.push(rc);
        studyIndex++; studyFlipped=false; renderStudy();
      });
    });
  }
}
document.getElementById('newDeckBtn').addEventListener('click', ()=>{
  const name = prompt('Deck name?'); if(!name) return;
    const tagsRaw = prompt('Tags (comma separated, optional)') || '';
    const tags = tagsRaw.split(',').map(t=>t.trim().toLowerCase()).filter(Boolean);
  const cards = []; let addMore=true;
  while(addMore && cards.length<20){
    const front = prompt('Front of card #'+(cards.length+1)+' (Cancel to stop)'); if(front===null) break;
    const back = prompt('Back of card #'+(cards.length+1)); if(back===null) break;
    cards.push(migrateCardForSpacedRepetition({id:uid(), front, back, known:false}));
    addMore = confirm('Add another card?');
  }
  if(cards.length){ decks.unshift({id:uid(), name, tags, cards, createdAt:Date.now()}); saveServerState(); renderDeckGrid(); }
});
function renderDeckTagFilterRow(){
    const row = document.getElementById('deckTagFilterRow');
    if(!row) return;
    const tagCounts = {};
    decks.forEach(d=>(d.tags||[]).forEach(t=>{ tagCounts[t] = (tagCounts[t]||0)+1; }));
    const tags = Object.keys(tagCounts).sort();
    if(!tags.length){ row.innerHTML = ''; return; }
    row.innerHTML = tags.map(t=>'<span class="tag-chip'+(activeDeckTagFilter===t?' active':'')+'" data-tag="'+escapeHtml(t)+'">'+escapeHtml(t)+' ('+tagCounts[t]+')</span>').join('');
    row.querySelectorAll('.tag-chip').forEach(chip=>{
          chip.addEventListener('click', ()=>{
                  const t = chip.dataset.tag;
                  activeDeckTagFilter = activeDeckTagFilter===t ? null : t;
                  renderDeckGrid();
          });
    });
}


/* ============ QUIZ MODE ============ */
function buildQuizQuestions(deck){
  const allOtherBacks = decks.flatMap(d=>d.cards).filter(c=>c.id).map(c=>c.back);
  const deckBacks = deck.cards.map(c=>c.back);
  const shuffled = deck.cards.slice().sort(()=>Math.random()-0.5);
  return shuffled.map(c=>{
    const pool = new Set();
    deckBacks.forEach(b=>{ if(b!==c.back) pool.add(b); });
    if(pool.size < 3){ allOtherBacks.forEach(b=>{ if(b!==c.back) pool.add(b); }); }
    const distractors = Array.from(pool).sort(()=>Math.random()-0.5).slice(0, 3);
    const options = [c.back, ...distractors].sort(()=>Math.random()-0.5);
    return { front: c.front, correct: c.back, options };
  });
}
function startQuiz(deckId){
  currentDeckId = deckId;
  const deck = decks.find(d=>d.id===deckId); if(!deck || deck.cards.length<2) return;
  quizQueue = buildQuizQuestions(deck); quizIndex=0; quizScore=0; quizAnswered=false;
  document.getElementById('deckGrid').style.display='none';
  document.getElementById('quizArea').style.display='block';
  renderQuiz();
}
function renderQuiz(){
  const area = document.getElementById('quizArea');
  const deck = decks.find(d=>d.id===currentDeckId);
  if(quizIndex >= quizQueue.length){
    const pct = quizQueue.length? Math.round(quizScore/quizQueue.length*100):0;
    area.innerHTML = '<h2 style="font-weight:700;">Quiz complete</h2>'+
      '<p style="color:var(--text-muted);margin-bottom:18px;">You scored <strong>'+quizScore+' / '+quizQueue.length+'</strong> ('+pct+'%).</p>'+
      '<div class="study-controls"><button class="sc-btn" id="quizRetry">Retry quiz</button><button class="btn primary" id="quizBackToDecks">Back to decks</button></div>';
    document.getElementById('quizRetry').addEventListener('click', ()=>startQuiz(currentDeckId));
    document.getElementById('quizBackToDecks').addEventListener('click', renderDeckGrid);
    return;
  }
  const q = quizQueue[quizIndex];
  let optionsHtml = q.options.map((opt,i)=>
    '<button class="quiz-option'+(isUrdu(opt)?' is-urdu urdu':'')+'" data-i="'+i+'">'+escapeHtml(opt)+'</button>'
  ).join('');
  area.innerHTML = '<div class="study-progress-text">Question '+(quizIndex+1)+' of '+quizQueue.length+' -- '+escapeHtml(deck.name)+' · Score: '+quizScore+'</div>'+
    '<div class="quiz-question'+(isUrdu(q.front)?' is-urdu urdu':'')+'">'+escapeHtml(q.front)+'</div>'+
    '<div class="quiz-options">'+optionsHtml+'</div>'+
    '<div class="study-controls" id="quizNextRow" style="display:none;"><button class="btn primary" id="quizNext">Next question</button></div>';
  quizAnswered = false;
  area.querySelectorAll('.quiz-option').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      if(quizAnswered) return;
      quizAnswered = true;
      const chosen = q.options[parseInt(btn.dataset.i,10)];
      area.querySelectorAll('.quiz-option').forEach(b=>{
        const val = q.options[parseInt(b.dataset.i,10)];
        if(val===q.correct) b.classList.add('correct');
        else if(b===btn) b.classList.add('wrong');
      });
      if(chosen===q.correct) quizScore++;
      document.getElementById('quizNextRow').style.display='flex';
    });
  });
  document.getElementById('quizNext').addEventListener('click', ()=>{ quizIndex++; renderQuiz(); });
}

/* ============ SETTINGS WIRING ============ */
document.querySelectorAll('[data-theme-opt]').forEach(el=> el.addEventListener('click', ()=>{ uiPrefs.theme=el.dataset.themeOpt; LS.set('zariya_ui_prefs',uiPrefs); applyUiPrefs(); }));
document.getElementById('themeToggleBtn').addEventListener('click', ()=>{ uiPrefs.theme = uiPrefs.theme==='dark'?'light':'dark'; LS.set('zariya_ui_prefs',uiPrefs); applyUiPrefs(); });
document.getElementById('fontSizeSlider').addEventListener('input', (e)=>{ uiPrefs.fontSize=parseInt(e.target.value,10); LS.set('zariya_ui_prefs',uiPrefs); applyUiPrefs(); });
document.getElementById('toggleTimestamps').addEventListener('click', ()=>{ uiPrefs.showTimestamps=!uiPrefs.showTimestamps; LS.set('zariya_ui_prefs',uiPrefs); applyUiPrefs(); renderChat(); });
document.getElementById('toggleTTS').addEventListener('click', ()=>{ uiPrefs.ttsEnabled=!uiPrefs.ttsEnabled; LS.set('zariya_ui_prefs',uiPrefs); applyUiPrefs(); });
document.getElementById('personaInput').addEventListener('input', (e)=>{ genPrefs.persona=e.target.value; LS.set('zariya_gen_prefs',genPrefs); });
document.getElementById('creativitySlider').addEventListener('input', (e)=>{ const pct=parseInt(e.target.value,10); genPrefs.temperature=pct/100; LS.set('zariya_gen_prefs',genPrefs); updateCreativityLabel(pct); });
document.getElementById('resetPersonaBtn').addEventListener('click', ()=>{ genPrefs={persona:'', temperature:0.5}; LS.set('zariya_gen_prefs',genPrefs); applyGenPrefs(); });

async function loadModelList(){
  const sel = document.getElementById('modelSelect');
  if(!sel) return;
  if(serverConfig.hostedMode){ sel.innerHTML = '<option value="">Local models are disabled on Vercel</option>'; return; }
  try{
    const data = await apiGet('/api/local-model/models');
    const models = data.models || [];
    const active = data.active || '';
    if(!models.length){
      sel.innerHTML = '<option value="">No models pulled yet (Ollama may not be running)</option>';
      return;
    }
    sel.innerHTML = models.map(m=> '<option value="'+escapeHtml(m.name)+'"'+(m.name===active?' selected':'')+'>'+escapeHtml(m.name)+(m.name===active?' (active)':'')+'</option>').join('');
  }catch(e){
    sel.innerHTML = '<option value="">Could not load models</option>';
  }
}
const modelSelect = document.getElementById('modelSelect');
if(modelSelect){
  modelSelect.addEventListener('change', async (e)=>{
    const name = e.target.value; if(!name) return;
    const note = document.getElementById('modelSwitchNote');
    note.textContent = 'Switching to '+name+'…';
    try{
      const res = await apiPost('/api/local-model/select', { model:name });
      if(res.ok){
        note.textContent = res.pulling ? ('Downloading '+name+'… this can take a few minutes.') : ('Now using '+name+'.');
        pollLocalModelStatus();
        const cfg = await apiGet('/api/config'); serverConfig = cfg; updateStatusPill(); renderAccountUI();
      } else {
        note.textContent = res.error || 'Could not switch model.';
      }
    }catch(err){ note.textContent = 'Could not reach the server.'; }
  });
}
const pullModelBtn = document.getElementById('pullModelBtn');
if(pullModelBtn){
  pullModelBtn.addEventListener('click', async ()=>{
    const inputEl = document.getElementById('newModelInput');
    const name = inputEl.value.trim(); if(!name) return;
    const note = document.getElementById('modelSwitchNote');
    note.textContent = 'Requesting '+name+'…';
    try{
      const res = await apiPost('/api/local-model/select', { model:name });
      if(res.ok){
        note.textContent = res.pulling ? ('Downloading '+name+'… this can take a few minutes.') : ('Now using '+name+'.');
        inputEl.value='';
        pollLocalModelStatus();
        loadModelList();
      } else {
        note.textContent = res.error || 'Could not pull that model.';
      }
    }catch(err){ note.textContent = 'Could not reach the server.'; }
  });
}

const localModelRetryBtn = document.getElementById('localModelRetryBtn');
if(localModelRetryBtn){
  localModelRetryBtn.addEventListener('click', async ()=>{
    localModelRetryBtn.disabled = true;
    const oldLabel = localModelRetryBtn.textContent;
    localModelRetryBtn.textContent = 'Retrying…';
    try{ await apiPost('/api/local-model/retry', {}); }catch(e){}
    try{
      const cfg = await apiGet('/api/config');
      serverConfig = cfg;
      updateStatusPill(); renderAccountUI();
    }catch(e){}
    localModelRetryBtn.disabled = false;
    localModelRetryBtn.textContent = oldLabel;
    pollLocalModelStatus();
  });
}

function downloadFile(filename, content){
  const blob = new Blob([content], {type:'text/plain;charset=utf-8'});
  const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=filename; a.click();
  URL.revokeObjectURL(a.href);
}

/* ============ LIVE STATUS POLLING ============ */
let statusPollTimer = null;
function pollLocalModelStatus(){
  if(serverConfig.hostedMode || serverConfig.localModelAvailable) return;
  if(statusPollTimer) clearInterval(statusPollTimer);
  let elapsed = 0;
  const intervalMs = 4000, maxMs = 15*60*1000;
  statusPollTimer = setInterval(async ()=>{
    elapsed += intervalMs;
    let cfg;
    try{ cfg = await apiGet('/api/config'); }catch(e){ return; }
    const changed = cfg.localModelAvailable !== serverConfig.localModelAvailable || cfg.localModelStatus !== serverConfig.localModelStatus;
    serverConfig = cfg;
    if(changed){ updateStatusPill(); renderAccountUI(); }
    if(cfg.localModelAvailable || elapsed >= maxMs) clearInterval(statusPollTimer);
  }, intervalMs);
}

/* ============ INIT ============ */
(async function init(){
  await loadServerState();
  applyUiPrefs();
  applyGenPrefs();
  loadModelList();
  updateStatusPill();
  renderAccountUI();
  renderSessionList();
  renderChat();
  pollLocalModelStatus();
})();
})();
