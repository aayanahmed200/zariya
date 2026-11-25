(function(){
"use strict";

/* ============ LOCAL UI PREFERENCES (theme/font/etc -- not API keys, those are server-side) ============ */
const LS = {
  get(k, d){ try{ const v = localStorage.getItem(k); return v===null? d : JSON.parse(v); }catch(e){ return d; } },
  set(k, v){ try{ localStorage.setItem(k, JSON.stringify(v)); return true; }catch(e){ return false; } }
};
const prefersDarkScheme = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
let uiPrefs = LS.get('zariya_ui_prefs', { theme: prefersDarkScheme?'dark':'light', fontSize:15, showTimestamps:true, ttsEnabled:false });
let genPrefs = LS.get('zariya_gen_prefs', { persona:'', temperature:0.5, responseStyle:'balanced' });
const responseStylePresets = {
  balanced:{
    label:'Balanced',
    description:'Clear answers with useful context',
    instruction:'Give clear, balanced answers with enough context to understand the point. Keep the structure easy to scan and avoid unnecessary repetition.'
  },
  concise:{
    label:'Concise',
    description:'Short, direct answers',
    instruction:'Be concise. Lead with the direct answer, keep paragraphs short, and avoid repeating points. Keep essential caveats and steps.'
  },
  steps:{
    label:'Step-by-step',
    description:'Ordered explanations and guidance',
    instruction:'When explaining a process or problem, break it into clear ordered steps and briefly explain why each step matters. Use examples only when useful.'
  },
  detailed:{
    label:'Detailed',
    description:'More context and worked examples',
    instruction:'Give thorough explanations with helpful context and examples. Organize longer answers into clear sections and avoid padding or repetition.'
  }
};

let sessions = [];
let notes = [];
let decks = [];
let currentSessionId = null;
let currentNoteId = null;
let currentDeckId = null;
let editingDeckId = null;
  let activeNoteTagFilter = null;
  let activeDeckTagFilter = null;
let studyQueue = []; let studyIndex = 0; let studyFlipped = false;
let editingIndex = null;
let isGenerating = false;
let voiceState = 'idle';
let shouldListen = false;
let isQuickToolBusy = false;
let activeGeneration = null;
let generationSequence = 0;
let serverConfig = {
  hostedMode:false, aiConfigured:false, aiAvailable:false,
  aiProvider:'Kilo AI Gateway', aiStatus:'Checking hosted AI…',
  aiModel:'kilo-auto/free',
  searchConfigured:false, githubConfigured:false,
  supabaseConfigured:false, storageMode:'browser'
};
function isPureUrdu(text){
  const value = String(text || '');
  return /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/.test(value) && !/[A-Za-z]/.test(value);
}
let me = { signedIn:false };

function uid(){ return Date.now().toString(36) + Math.random().toString(36).slice(2,8); }
function nowISO(){ return new Date().toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}); }
function isUrdu(text){ return /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/.test(String(text||'')); }
function syncUrduInput(element){
  if(!element) return;
  const hasUrdu=isUrdu(element.value);
  element.classList.toggle('input-urdu',hasUrdu);
  element.dir=isPureUrdu(element.value)?'rtl':'auto';
}
function wrapUrduRuns(value){
  const arabicRun=/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+(?:[\s\u200C\u200D،؛؟۔٪٫٬]+[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)*/g;
  return String(value??'').replace(arabicRun,run=>'<span class="urdu-run" lang="ur" dir="rtl">'+run+'</span>');
}
function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
function formatInline(value){
  const protectedHtml = [];
  let text = String(value ?? '');
  const hold = markup=>{
    const marker = '\u0000'+protectedHtml.length+'\u0000';
    protectedHtml.push(markup);
    return marker;
  };
  text = text.replace(/\x60([^\x60\n]+)\x60/g, (match, code)=>hold('<code>'+escapeHtml(code)+'</code>'));
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (match, label, url)=>{
    return hold('<a href="'+escapeHtml(url)+'" target="_blank" rel="noopener noreferrer">'+wrapUrduRuns(escapeHtml(label))+'</a>');
  });
  text = escapeHtml(text);
  text = text.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  text = text.replace(/~~(.+?)~~/g,'<del>$1</del>');
  text = text.replace(/(^|[^\w*])\*([^*\n]+)\*(?!\*)/g,'$1<em>$2</em>');
  text = text.replace(/(^|[^\w_])_([^_\n]+)_(?!\w)/g,'$1<em>$2</em>');
  text = wrapUrduRuns(text);
  text = text.replace(/\n/g,'<br>');
  text = text.replace(/\u0000(\d+)\u0000/g, (match, index)=>protectedHtml[Number(index)] || '');
  return text;
}
function renderSearchResultsHtml(query, results){
  const heading = formatInline('**Web search results for "'+query+'"**');
  const cards = results.map(result=>{
    const title = wrapUrduRuns(escapeHtml(result.title || result.link || 'Untitled result'));
    const rawUrl = String(result.link || '');
    let safeUrl = '';
    try{
      const parsed = new URL(rawUrl);
      if(parsed.protocol==='http:' || parsed.protocol==='https:') safeUrl = escapeHtml(rawUrl);
    }catch(error){}
    const snippet = wrapUrduRuns(escapeHtml(result.snippet || ''));
    return '<div class="search-result">'
      +(safeUrl?'<a class="sr-title" href="'+safeUrl+'" target="_blank" rel="noopener noreferrer">'+title+'</a>':'<span class="sr-title">'+title+'</span>')
      +'<div class="sr-url">'+safeUrl+'</div>'
      +'<div class="sr-snippet">'+snippet+'</div>'
      +'</div>';
  }).join('');
  return heading+cards;
}
function renderMarkdown(raw){
  const lines = String(raw ?? '').replace(/\r\n?/g,'\n').split('\n');
  const html = [];
  const cells = line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(cell=>cell.trim());
  const isTableSeparator = line=>cells(line).length>0 && cells(line).every(cell=>/^:?-{3,}:?$/.test(cell));
  const isTableStart = index=>index+1<lines.length && /^\s*\|/.test(lines[index]) && isTableSeparator(lines[index+1]);
  const isListLine = line=>/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line);
  const isBlockStart = index=>{
    const line = lines[index] || '';
    return /^ {0,3}\x60{3}/.test(line) || /^ {0,3}#{1,6}\s/.test(line)
      || /^ {0,3}(?:-{3,}|_{3,}|\*{3,})\s*$/.test(line)
      || /^\s*>/.test(line) || isListLine(line) || isTableStart(index);
  };
  let i=0;
  while(i<lines.length){
    const line = lines[i];
    if(!line.trim()){ i++; continue; }
    const fence = line.match(/^ {0,3}\x60{3}\s*([\w.+-]*)\s*$/);
    if(fence){
      const language = fence[1] || 'code';
      const codeLines = [];
      i++;
      while(i<lines.length && !/^ {0,3}\x60{3}\s*$/.test(lines[i])) codeLines.push(lines[i++]);
      if(i<lines.length) i++;
      const codeId = 'code_'+uid();
      html.push('<div class="code-block"><div class="code-block-head"><span>'+escapeHtml(language)+'</span><button class="code-copy-btn" type="button" data-code-id="'+codeId+'">Copy</button></div><pre><code dir="ltr" id="'+codeId+'">'+escapeHtml(codeLines.join('\n'))+'</code></pre></div>');
      continue;
    }
    const heading = line.match(/^ {0,3}(#{1,6})\s+(.+)$/);
    if(heading){
      const level = heading[1].length;
      html.push('<h'+level+' dir="auto">'+formatInline(heading[2])+'</h'+level+'>');
      i++; continue;
    }
    if(/^ {0,3}(?:-{3,}|_{3,}|\*{3,})\s*$/.test(line)){
      html.push('<hr class="markdown-rule">');
      i++; continue;
    }
    if(/^\s*>/.test(line)){
      const quote = [];
      while(i<lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ''));
      html.push('<blockquote dir="auto">'+renderMarkdown(quote.join('\n'))+'</blockquote>');
      continue;
    }
    if(isTableStart(i)){
      const headers = cells(lines[i]);
      i += 2;
      const rows = [];
      while(i<lines.length && /^\s*\|/.test(lines[i])){ rows.push(cells(lines[i])); i++; }
      const headHtml = headers.map(cell=>'<th scope="col" dir="auto">'+formatInline(cell)+'</th>').join('');
      const bodyHtml = rows.map(row=>'<tr>'+headers.map((header,index)=>'<td dir="auto">'+formatInline(row[index] || '')+'</td>').join('')+'</tr>').join('');
      html.push('<div class="markdown-table-wrap"><table class="markdown-table"><thead><tr>'+headHtml+'</tr></thead><tbody>'+bodyHtml+'</tbody></table></div>');
      continue;
    }
    if(/^\s*[-*+]\s+/.test(line)){
      const items = [];
      while(i<lines.length && /^\s*[-*+]\s+/.test(lines[i])){ items.push('<li dir="auto">'+formatInline(lines[i].replace(/^\s*[-*+]\s+/,''))+'</li>'); i++; }
      html.push('<ul>'+items.join('')+'</ul>');
      continue;
    }
    if(/^\s*\d+[.)]\s+/.test(line)){
      const items = [];
      while(i<lines.length && /^\s*\d+[.)]\s+/.test(lines[i])){ items.push('<li dir="auto">'+formatInline(lines[i].replace(/^\s*\d+[.)]\s+/,''))+'</li>'); i++; }
      html.push('<ol>'+items.join('')+'</ol>');
      continue;
    }
    const paragraph = [];
    while(i<lines.length && lines[i].trim() && !isBlockStart(i)){ paragraph.push(lines[i]); i++; }
    if(paragraph.length) html.push('<p dir="auto">'+formatInline(paragraph.join('\n'))+'</p>');
  }
  return html.join('');
}

/* ============ API HELPERS ============ */
async function readApiResponse(response){
  let data;
  try{ data = await response.json(); }
  catch(e){ throw new Error('The server returned an unreadable response (HTTP '+response.status+').'); }
  if(!response.ok) throw new Error(data.error || data.status || ('Request failed (HTTP '+response.status+').'));
  return data;
}
async function apiGet(url){
  return readApiResponse(await fetch(url, { headers:{'Accept':'application/json'} }));
}
async function apiPost(url, body, signal){
  return readApiResponse(await fetch(url, { method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body:JSON.stringify(body||{}), signal }));
}

function updateStorageIndicators(){
  const synced=!!(serverConfig.supabaseConfigured && stateBackendAvailable && !localStateMessage);
  const profileName=document.getElementById('sbProfileName');
  const caption=document.getElementById('storageCaption');
  if(profileName) profileName.textContent=synced ? 'Cloud workspace' : 'Saved in this browser';
  if(caption) caption.textContent=synced ? 'Synced to cloud' : 'Stored on this device';
}
async function updateStorageStatus(saved=true, message=''){
  updateStorageIndicators();
  const status=document.getElementById('storageStatus');
  if(!status) return;
  status.classList.toggle('warning',!saved);
  status.textContent=message || (saved
    ? (serverConfig.supabaseConfigured ? 'Synced securely with Supabase.' : 'All changes saved on this device.')
    : 'This browser could not save more data. Export a backup and free up browser storage.');
}
function exportWorkspaceBackup(){
  const backup={
    format:'zariya-workspace-backup',
    version:1,
    exportedAt:new Date().toISOString(),
    sessions,notes,decks
  };
  const date=new Date().toISOString().slice(0,10);
  downloadFile('zariya-workspace-'+date+'.json',JSON.stringify(backup,null,2),'application/json;charset=utf-8');
  updateStorageStatus(true,'Workspace backup exported. Keep the file somewhere safe.');
}
function safeImportedText(value,maxLength,fallback=''){
  return typeof value==='string' ? value.slice(0,maxLength) : fallback;
}
function normaliseImportedWorkspace(source){
  if(!source || typeof source!=='object' || source.format!=='zariya-workspace-backup' || source.version!==1){
    throw new Error('This file is not a supported Zariya workspace backup.');
  }
  if(!Array.isArray(source.sessions) || !Array.isArray(source.notes) || !Array.isArray(source.decks)){
    throw new Error('The backup is missing chats, notes or flashcards data.');
  }
  if(source.sessions.length>500 || source.notes.length>1000 || source.decks.length>500){
    throw new Error('This backup contains more items than Zariya can safely restore at once.');
  }
  let messageCount=0;
  const restoredSessions=source.sessions.map(item=>{
    if(!item || typeof item!=='object') return null;
    const messages=Array.isArray(item.messages) ? item.messages.slice(0,5000).flatMap(message=>{
      if(!message || !['user','assistant'].includes(message.role) || typeof message.content!=='string') return [];
      messageCount+=1;
      if(messageCount>10000) return [];
      return [{
        role:message.role,
        content:message.content.slice(0,50000),
        ts:safeImportedText(message.ts,80,nowISO())
      }];
    }) : [];
    return {
      id:uid(),
      title:safeImportedText(item.title,120,'Imported chat') || 'Imported chat',
      messages,
      createdAt:Number.isFinite(Number(item.createdAt)) ? Number(item.createdAt) : Date.now()
    };
  }).filter(Boolean);
  const restoredNotes=source.notes.map(item=>{
    if(!item || typeof item!=='object') return null;
    return {
      id:uid(),
      title:safeImportedText(item.title,180,'Untitled note') || 'Untitled note',
      body:safeImportedText(item.body,150000),
      tags:Array.isArray(item.tags) ? item.tags.filter(tag=>typeof tag==='string').slice(0,20).map(tag=>tag.trim().toLowerCase().slice(0,40)).filter(Boolean) : [],
      updatedAt:Number.isFinite(Number(item.updatedAt)) ? Number(item.updatedAt) : Date.now()
    };
  }).filter(Boolean);
  const restoredDecks=source.decks.map(item=>{
    if(!item || typeof item!=='object' || !Array.isArray(item.cards)) return null;
    const cards=item.cards.slice(0,30).flatMap(card=>{
      if(!card || typeof card.front!=='string' || typeof card.back!=='string') return [];
      const ease=Number(card.ease);
      const interval=Number(card.interval);
      const reps=Number(card.reps);
      const due=typeof card.due==='string' && Number.isFinite(Date.parse(card.due))
        ? card.due : new Date(0).toISOString();
      return [migrateCardForSpacedRepetition({
        id:uid(),
        front:card.front.slice(0,600),
        back:card.back.slice(0,2400),
        known:!!card.known,
        ease:Number.isFinite(ease) ? Math.min(4,Math.max(1.3,ease)) : 2.5,
        interval:Number.isFinite(interval) ? Math.max(0,Math.min(36500,interval)) : 0,
        reps:Number.isFinite(reps) ? Math.max(0,Math.min(100000,reps)) : 0,
        due
      })];
    });
    return {
      id:uid(),
      name:safeImportedText(item.name,100,'Imported deck') || 'Imported deck',
      tags:Array.isArray(item.tags) ? item.tags.filter(tag=>typeof tag==='string').slice(0,20).map(tag=>tag.trim().toLowerCase().slice(0,40)).filter(Boolean) : [],
      cards,
      createdAt:Number.isFinite(Number(item.createdAt)) ? Number(item.createdAt) : Date.now()
    };
  }).filter(Boolean);
  return {sessions:restoredSessions,notes:restoredNotes,decks:restoredDecks};
}
function restoreWorkspaceBackup(raw){
  let source;
  try{ source=JSON.parse(raw); }
  catch(error){ throw new Error('The selected file is not valid JSON.'); }
  const restored=normaliseImportedWorkspace(source);
  const itemCount=restored.sessions.length+restored.notes.length+restored.decks.length;
  if(!itemCount) throw new Error('This backup does not contain any chats, notes or flashcard decks.');
  if(!confirm('Restore this backup and replace the chats, notes and flashcard decks currently saved in this browser? Export your current workspace first if you want to keep it.')) return false;
  sessions=restored.sessions;
  notes=restored.notes;
  decks=restored.decks;
  currentSessionId=sessions.length ? sessions[0].id : null;
  currentNoteId=null;
  currentDeckId=null;
  editingDeckId=null;
  activeNoteTagFilter=null;
  activeDeckTagFilter=null;
  saveServerState();
  renderSessionList();
  renderChat();
  renderNotesList();
  renderDeckGrid();
    return true;
}
document.getElementById('exportWorkspaceBtn').addEventListener('click',exportWorkspaceBackup);
document.getElementById('importWorkspaceBtn').addEventListener('click',()=>document.getElementById('importWorkspaceFile').click());
document.getElementById('importWorkspaceFile').addEventListener('change',event=>{
  const file=event.target.files && event.target.files[0];
  if(!file) return;
  if(file.size>25*1024*1024){
    updateStorageStatus(false,'That backup is larger than 25 MB. Choose a smaller backup file.');
    event.target.value='';
    return;
  }
  const reader=new FileReader();
  reader.onload=()=>{
    try{
      restoreWorkspaceBackup(String(reader.result||''));
    }catch(error){
      updateStorageStatus(false,error.message || 'Could not restore that backup.');
    }
  };
  reader.onerror=()=>updateStorageStatus(false,'The backup file could not be read.');
  reader.readAsText(file);
  event.target.value='';
});

let stateBackendAvailable = false;
let localStateMessage = '';

function localWorkspaceStateKey(){
  return 'zariya_app_state_v1:' + (me.signedIn && me.login ? me.login : 'guest');
}
function emptyWorkspaceState(){
  return window.ZariyaWorkspaceSync.empty();
}
function workspaceHasItems(state){
  return ['sessions','notes','decks'].some(key=>Array.isArray(state && state[key]) && state[key].length>0);
}
function mergeWorkspaceState(remote, cached){
  return window.ZariyaWorkspaceSync.merge(remote,cached);
}

async function loadServerState(){
  const results = await Promise.allSettled([apiGet('/api/config'), apiGet('/api/me')]);
  serverConfig = results[0].status === 'fulfilled' ? results[0].value : {
    hostedMode:true, aiConfigured:false, aiAvailable:false, aiProvider:'Kilo AI Gateway',
    aiStatus:'The app server could not be reached. Refresh to retry.',
    aiModel:'kilo-auto/free', searchConfigured:false, githubConfigured:false,
    supabaseConfigured:false, storageMode:'browser'
  };
  me = results[1].status === 'fulfilled' ? results[1].value : { signedIn:false, githubConfigured:false };

  const stateKey=localWorkspaceStateKey();
  const cached=LS.get(stateKey,emptyWorkspaceState());
  let state=cached;
  stateBackendAvailable=false;
  localStateMessage='';

  if(serverConfig.supabaseConfigured || !serverConfig.hostedMode){
    try{
      const remote=await apiGet('/api/state');
      stateBackendAvailable=true;
      if(serverConfig.supabaseConfigured){
        state=window.ZariyaWorkspaceSync.stamp(mergeWorkspaceState(remote,cached),remote);
        if(JSON.stringify(state)!==JSON.stringify(remote)){
          try{
            await apiPost('/api/state',state);
          }catch(syncError){
            localStateMessage='Some local changes could not be synced yet. They are still saved in this browser.';
          }
        }
      }else{
        state=remote;
      }
      LS.set(stateKey,state);
    }catch(error){
      state=cached;
      stateBackendAvailable=false;
      localStateMessage=serverConfig.supabaseConfigured
        ? 'Cloud sync is unavailable. Your changes are being kept in this browser.'
        : 'The local server could not be reached. Your changes are being kept in this browser.';
    }
  }else{
    localStateMessage='Saved in this browser only. Connect Supabase to sync across devices.';
  }

  sessions = Array.isArray(state.sessions) ? state.sessions : [];
  notes = Array.isArray(state.notes) ? state.notes : [];
  decks = Array.isArray(state.decks) ? state.decks : [];
  decks.forEach(d=> (Array.isArray(d.cards) ? d.cards : []).forEach(migrateCardForSpacedRepetition));
  currentSessionId = sessions.length ? sessions[0].id : null;

  const storageDescription=document.getElementById('storageDescription');
  if(storageDescription){
    storageDescription.textContent=serverConfig.supabaseConfigured
      ? 'Your workspace syncs securely across devices.'
      : (serverConfig.hostedMode
        ? 'Your workspace is saved in this browser only.'
        : 'Your workspace is saved by this local development server.');
  }
  const backupDescription=document.getElementById('workspaceBackupDescription');
  if(backupDescription){
    backupDescription.textContent=serverConfig.supabaseConfigured
      ? 'Chats, notes and flashcards sync to your account. You can still export a private backup at any time.'
      : 'Chats, notes and flashcards are saved in this browser only. Export a backup before clearing browser data or moving devices.';
  }
  const githubStorageNote=document.getElementById('githubStorageNote');
  if(githubStorageNote){
    githubStorageNote.textContent=serverConfig.supabaseConfigured
      ? 'With Supabase connected, your workspace syncs across devices for this GitHub account.'
      : 'GitHub sign-in identifies your profile. Without Supabase, chats, notes and flashcards remain on this device.';
  }
  updateStorageStatus((stateBackendAvailable || !serverConfig.hostedMode) && !localStateMessage,
    localStateMessage || (serverConfig.supabaseConfigured && stateBackendAvailable
      ? 'Connected to Supabase. Workspace data is synced.'
      : (serverConfig.hostedMode
        ? 'Saved in this browser only.'
        : 'Saved by this local development server.')));
}
let saveTimer;
let cloudSaveQueue=Promise.resolve();
function saveCloudSnapshot(snapshot){
  const pending=cloudSaveQueue.catch(()=>{}).then(()=>apiPost('/api/state',snapshot));
  cloudSaveQueue=pending.then(()=>undefined,()=>undefined);
  return pending;
}
function saveServerState(){
  clearTimeout(saveTimer);
  const stateKey=localWorkspaceStateKey();
  const previous=LS.get(stateKey,emptyWorkspaceState());
  const snapshot=window.ZariyaWorkspaceSync.stamp({sessions,notes,decks,_deleted:previous._deleted},previous);
  sessions=snapshot.sessions;
  notes=snapshot.notes;
  decks=snapshot.decks;
  const saved=LS.set(stateKey,snapshot);

  if(serverConfig.supabaseConfigured){
    saveTimer=setTimeout(async()=>{
      try{
        await saveCloudSnapshot(snapshot);
        stateBackendAvailable=true;
        localStateMessage='';
        updateStorageStatus(true,'Synced securely with Supabase.');
      }catch(error){
        stateBackendAvailable=false;
        localStateMessage='Cloud sync failed. Your changes are saved in this browser; retry after reconnecting.';
        updateStorageStatus(saved,saved
          ? localStateMessage
          : 'Cloud sync failed and this browser could not save more data. Export a backup.');
      }
    },350);
    if(!saved) updateStorageStatus(false,'Saving to Supabase. Browser storage is unavailable.');
    return true;
  }

  if(serverConfig.hostedMode){
    updateStorageStatus(saved,saved
      ? (localStateMessage || 'Saved in this browser only. Connect Supabase to sync across devices.')
      : 'This browser could not save more data. Export a backup and free up browser storage.');
    return saved;
  }

  saveTimer=setTimeout(async()=>{
    try{
      await apiPost('/api/state',snapshot);
      updateStorageStatus(true,'Saved by this local development server.');
    }catch(error){
      updateStorageStatus(saved,saved
        ? 'The local server could not be reached. Your changes are saved in this browser.'
        : 'The local server and browser storage could not save your changes. Export a backup.');
    }
  },350);
  return true;
}


/* ============ THEME / UI PREFS ============ */
function applyUiPrefs(){
  document.documentElement.setAttribute('data-theme', uiPrefs.theme);
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  if(themeColorMeta) themeColorMeta.setAttribute('content', uiPrefs.theme==='dark' ? '#171d19' : '#faf9f6');
  document.querySelectorAll('[data-theme-opt]').forEach(el=>{
    const active=el.dataset.themeOpt===uiPrefs.theme;
    el.classList.toggle('active',active);
    el.setAttribute('aria-pressed',String(active));
  });
  document.getElementById('fontSizeSlider').value = uiPrefs.fontSize;
  document.getElementById('fontSizeLabel').textContent = uiPrefs.fontSize+'px';
  document.documentElement.style.setProperty('--chat-font-size', uiPrefs.fontSize+'px');
  const timestampsToggle=document.getElementById('toggleTimestamps');
  const ttsToggle=document.getElementById('toggleTTS');
  timestampsToggle.classList.toggle('on',uiPrefs.showTimestamps);
  timestampsToggle.setAttribute('aria-pressed',String(!!uiPrefs.showTimestamps));
  ttsToggle.classList.toggle('on',uiPrefs.ttsEnabled);
  ttsToggle.setAttribute('aria-pressed',String(!!uiPrefs.ttsEnabled));
}
function setResponseStyle(style,persist=true){
  if(!Object.prototype.hasOwnProperty.call(responseStylePresets,style)) style='balanced';
  genPrefs.responseStyle=style;
  const preset=responseStylePresets[style];
  const label=document.getElementById('responsePresetLabel');
  const trigger=document.getElementById('responsePresetTrigger');
  if(label) label.textContent=preset.label;
  if(trigger) trigger.setAttribute('aria-label','Response style: '+preset.label);
  document.querySelectorAll('[data-response-style]').forEach(option=>{
    option.setAttribute('aria-selected',String(option.dataset.responseStyle===style));
  });
  if(persist) LS.set('zariya_gen_prefs',genPrefs);
}
function applyGenPrefs(){
  const personaInput=document.getElementById('personaInput');
  personaInput.value = genPrefs.persona || '';
  syncUrduInput(personaInput);
  const pct = Math.round((typeof genPrefs.temperature==='number'? genPrefs.temperature : 0.5) * 100);
  document.getElementById('creativitySlider').value = pct;
  updateCreativityLabel(pct);
  setResponseStyle(genPrefs.responseStyle||'balanced',false);
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
  const dot=document.getElementById('statusDot');
  const text=document.getElementById('statusText');
  if(serverConfig.aiAvailable){
    dot.classList.remove('off');
    text.textContent='Free AI';
  }else{
    dot.classList.add('off');
    text.textContent='AI unavailable';
  }
  const hint=document.getElementById('composerHint');
  if(hint && !isGenerating){
    hint.textContent=serverConfig.aiAvailable
      ? 'Free hosted AI · no install, account, or personal API key. Shared usage limits apply.'
      : 'Free AI is temporarily unavailable. Your saved chats are still here; try again shortly.';
  }
}
function renderAccountUI(){
  const sbAvatar=document.getElementById('sbProfileAvatar');
  const sbName=document.getElementById('sbProfileName');
  const signedOutRow=document.getElementById('accountSignedOutRow');
  const signedInRow=document.getElementById('accountSignedInRow');
  const configNote=document.getElementById('githubConfigNote');

  if(me.signedIn){
    sbName.textContent=me.name || me.login;
    sbAvatar.innerHTML='<img src="'+escapeHtml(me.avatar||'/static/logo.png')+'" alt="">';
    signedOutRow.style.display='none';
    signedInRow.style.display='flex';
    document.getElementById('accountAvatar').src=me.avatar || '/static/logo.png';
    document.getElementById('accountName').textContent=me.name || me.login;
    document.getElementById('accountBio').textContent=me.bio || '';
  }else{
    sbName.textContent=serverConfig.githubConfigured ? 'Sign in with GitHub' : 'Guest workspace';
    sbAvatar.textContent='Z';
    signedOutRow.style.display='flex';
    signedInRow.style.display='none';
  }
  const setupPanel=document.getElementById('githubSetupPanel');
  const signInButton=document.getElementById('githubSignInBtn');
  if(serverConfig.githubConfigured){
    configNote.textContent='Connect your GitHub profile. Your workspace data remains saved on this device.';
    signInButton.disabled=false;
    signInButton.querySelector('span').textContent='Sign in with GitHub';
    if(setupPanel) setupPanel.hidden=true;
  }else{
    configNote.textContent='One-time setup is needed before GitHub sign-in can be used. Select the button for the exact setup details.';
    signInButton.disabled=false;
    signInButton.querySelector('span').textContent='Set up GitHub sign-in';
  }

  const modelStatus=document.getElementById('aiModelStatusText');
  if(modelStatus) modelStatus.textContent=serverConfig.aiStatus || 'Checking hosted model…';
  const modelName=document.getElementById('aiModelName');
  if(modelName) modelName.textContent=serverConfig.aiModel || 'Hosted open model';
  const providerNote=document.getElementById('aiProviderNote');
  if(providerNote) providerNote.textContent=serverConfig.aiAvailable
    ? 'Connected to Kilo’s anonymous free-model pool. No account or personal API key is needed; shared limits apply.'
    : 'The free model pool is not responding right now. Zariya will show a clear service error rather than invent an AI answer.';
  const statusMark=document.getElementById('aiStatusMark');
  if(statusMark) statusMark.style.background=serverConfig.aiAvailable ? 'var(--success)' : 'var(--muted)';

  const searchStatus=document.getElementById('searchStatusText');
  if(searchStatus) searchStatus.textContent=serverConfig.searchConfigured ? 'Available' : 'Not configured';
  const searchTool=document.querySelector('[data-tool="websearch"]');
  if(searchTool) searchTool.hidden=!serverConfig.searchConfigured;
  updateOnboardingBanner();
}
  const ONBOARDING_DISMISS_KEY = 'zariya_onboarding_dismissed';
  function updateOnboardingBanner(){
      const banner = document.getElementById('onboardingBanner');
      if(!banner) return;
      const dismissed = LS.get(ONBOARDING_DISMISS_KEY, false);
      const needsHelp = !serverConfig.aiAvailable;
      const copy = banner.querySelector('.ob-text');
      if(copy) copy.textContent = 'Hosted AI is temporarily unavailable. You can still use Zariya’s built-in knowledge mode and try chat again shortly.';
      banner.style.display = (needsHelp && !dismissed) ? 'flex' : 'none';
  }
  const onboardingDismissBtn = document.getElementById('onboardingDismissBtn');
  if(onboardingDismissBtn) onboardingDismissBtn.addEventListener('click', ()=>{ LS.set(ONBOARDING_DISMISS_KEY, true); updateOnboardingBanner(); });
document.getElementById('sbProfileRow').addEventListener('click', ()=>switchView('settings'));
document.getElementById('githubSignInBtn').addEventListener('click', ()=>{
  if(serverConfig.githubConfigured){
    window.location.href = '/auth/github/login';
    return;
  }
  const setupPanel=document.getElementById('githubSetupPanel');
  if(setupPanel){
    setupPanel.hidden=false;
    setupPanel.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
});
document.getElementById('copyGithubCallbackBtn').addEventListener('click', async ()=>{
  const status=document.getElementById('accountAuthStatus');
  const value='https://zariyas.vercel.app/auth/github/callback';
  try{
    if(!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('Clipboard unavailable');
    await navigator.clipboard.writeText(value);
    status.textContent='Callback URL copied.';
    status.hidden=false;
  }catch(error){
    status.textContent='Copy is not available in this browser. Select the callback URL above and copy it manually.';
    status.hidden=false;
  }
});
document.getElementById('githubSignOutBtn').addEventListener('click', async ()=>{
  const button=document.getElementById('githubSignOutBtn');
  button.disabled=true;
  try{
    const response=await fetch('/auth/logout', { method:'POST' });
    if(!response.ok) throw new Error('Could not sign out. Please try again.');
    me = { signedIn:false };
    await loadServerState();
    renderAccountUI();renderSessionList();renderChat();
  }catch(error){
    const status=document.getElementById('accountAuthStatus');
    status.textContent=error.message||'Could not sign out. Please try again.';
    status.hidden=false;
  }finally{
    button.disabled=false;
  }
});
const authError=new URLSearchParams(window.location.search).get('authError');
if(authError){
  const status=document.getElementById('accountAuthStatus');
  status.textContent=authError;
  status.hidden=false;
  window.history.replaceState({},'',window.location.pathname+window.location.hash);
  document.getElementById('githubSetupPanel').hidden=!serverConfig.githubConfigured;
}

/* ============ VIEW SWITCHING ============ */
function switchView(name){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.getElementById('view-'+name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active', n.dataset.view===name));
  const title=document.getElementById('topbarSection');
  if(title) title.textContent = ({chat:'Chat',notepad:'Notepad',flashcards:'Flashcards',settings:'Settings'})[name] || 'Workspace';
  document.getElementById('quickTools').style.display = name==='chat' ? '' : 'none';
  closeSidebarMobile();
  if(name==='notepad') renderNotesList();
  if(name==='flashcards') renderDeckGrid();
  if(name==='settings') renderAccountUI();
}
document.querySelectorAll('[data-view]').forEach(n=> n.addEventListener('click', ()=>switchView(n.dataset.view)));

function openSidebarMobile(){
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sbScrim').classList.add('show');
  document.getElementById('hamburgerBtn').setAttribute('aria-expanded','true');
}
function closeSidebarMobile(){
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sbScrim').classList.remove('show');
  document.getElementById('hamburgerBtn').setAttribute('aria-expanded','false');
}
document.getElementById('hamburgerBtn').addEventListener('click', openSidebarMobile);
document.getElementById('sbScrim').addEventListener('click', closeSidebarMobile);

/* ============ SESSIONS ============ */
function newSession(){
  if(isGenerating) stopGenerating();
  const s = { id:uid(), title:'New chat', messages:[], createdAt:Date.now() };
  sessions.unshift(s); currentSessionId = s.id;
  switchView('chat');
  saveServerState(); renderSessionList(); renderChat();
}
function currentSession(){ return sessions.find(s=>s.id===currentSessionId); }
function deleteSession(id, ev){
  ev.stopPropagation();
  if(isGenerating && id===currentSessionId) stopGenerating();
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
  if(!filtered.length){
    const empty=document.createElement('div');
    empty.className='sess-empty';
    empty.textContent=q ? 'No matching chats' : 'No chats yet';
    if(q){
      const clear=document.createElement('button');
      clear.type='button';
      clear.textContent='Clear search';
      clear.addEventListener('click',()=>{
        document.getElementById('sessSearch').value='';
        renderSessionList();
        document.getElementById('sessSearch').focus();
      });
      empty.appendChild(clear);
    }
    wrap.appendChild(empty);
  }
  filtered.forEach(s=>{
    const div = document.createElement('div');
    div.className = 'sess-item' + (s.id===currentSessionId?' active':'');
    div.tabIndex = 0;
    div.setAttribute('role','button');
    div.setAttribute('aria-current', s.id===currentSessionId ? 'true' : 'false');
    div.innerHTML = '<span class="sess-title">'+escapeHtml(s.title)+'</span><button class="sess-del" title="Delete chat" aria-label="Delete chat"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6"/></svg></button>';
    div.addEventListener('click', ()=>{
      if(isGenerating && currentSessionId!==s.id) stopGenerating();
      currentSessionId = s.id;
      editingIndex=null;
      switchView('chat');
      renderSessionList();
      renderChat();
    });
    div.addEventListener('keydown', (e)=>{
      if(e.target !== div) return;
      if(e.key==='Enter' || e.key===' '){ e.preventDefault(); div.click(); }
    });
    div.querySelector('.sess-del').addEventListener('click', (e)=>deleteSession(s.id, e));
    wrap.appendChild(div);
  });
}
document.getElementById('sessSearch').addEventListener('input', renderSessionList);
document.getElementById('newChatBtn').addEventListener('click', newSession);
document.addEventListener('keydown', e=>{
  if((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==='k'){
    e.preventDefault();
    newSession();
    input.focus();
  }
  if(e.key==='Escape') closeSidebarMobile();
});


/* ============ CHAT RENDER ============ */
function renderChat(){
  const inner = document.getElementById('chat-inner');
  const scroll = document.getElementById('chat-scroll');
  const session = currentSession();
  updateQuickToolsState();
  inner.innerHTML = '';
  if(!session || !session.messages.length){
    scroll.classList.add('empty-mode'); inner.classList.add('empty-mode');
    const hero = document.createElement('div');
    hero.className = 'empty-hero';
    hero.innerHTML = '<div class="hero-kicker">URDU · ENGLISH · MORE</div><h1>What would you like to work on?</h1><div class="urdu-line" lang="ur" dir="rtl">آئیے کچھ نیا سیکھتے ہیں</div><p>Ask a question, explore an idea, or practise something you are learning.</p>';
    const suggestions = document.createElement('div');
    suggestions.className = 'home-suggestions';
    ['Explain a difficult topic in simple words','Translate a sentence into Urdu','Help me revise for an exam','Summarise these notes'].forEach(label=>{
      const button=document.createElement('button');
      button.type='button'; button.className='suggest-card'; button.textContent=label;
      button.addEventListener('click',()=>{
        input.value=label;
        input.dispatchEvent(new Event('input',{bubbles:true}));
        sendMessage();
      });
      suggestions.appendChild(button);
    });
    hero.appendChild(suggestions);
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

  const urduClass = isPureUrdu(m.content) ? 'is-urdu' : '';
  if(m.role==='user'){
    row.innerHTML = '<div class="bubble-col user-col"><div class="bubble user '+urduClass+'" dir="auto">'+formatInline(m.content)+'</div>'+
      (uiPrefs.showTimestamps ? '<div class="msg-meta">'+(m.ts||'')+'</div>' : '')+
      '<div class="msg-actions"><button class="ghost-btn" data-act="edit">Edit</button></div></div>';
    row.querySelector('[data-act="edit"]').addEventListener('click', ()=>{ editingIndex=idx; renderChat(); });
  } else {
    row.innerHTML = '<img class="avatar-logo" src="/static/logo.png" alt=""><div class="bubble-col assistant-col"><div class="bubble assistant '+urduClass+'" dir="auto">'+(m.html || renderMarkdown(m.content))+'</div>'+
      (uiPrefs.showTimestamps ? '<div class="msg-meta">'+(m.ts||'')+'</div>' : '')+
      '<div class="msg-actions"><button class="ghost-btn" data-act="copy">Copy</button><button class="ghost-btn" data-act="speak">Read aloud</button><button class="ghost-btn" data-act="up" title="Good answer">Helpful</button><button class="ghost-btn" data-act="down" title="Not helpful">Not helpful</button>'+
      (isLast?'<button class="ghost-btn" data-act="regen">Regenerate</button>':'')+'</div></div>';
    row.querySelector('[data-act="copy"]').addEventListener('click', event=>copyMessageContent(event.currentTarget,m.content));
    row.querySelector('[data-act="speak"]').addEventListener('click', event=>{
      const button=event.currentTarget;
      if(!speak(m.content)){
        const original=button.textContent;
        button.textContent='Speech unavailable';
        window.setTimeout(()=>{if(button.isConnected) button.textContent=original;},1800);
      }
    });
    const regen = row.querySelector('[data-act="regen"]');
    if(regen) regen.addEventListener('click', regenerateLast);
    const upBtn = row.querySelector('[data-act="up"]');
    if(upBtn) upBtn.addEventListener('click', ()=>sendFeedback(idx, 'up', upBtn));
    const downBtn = row.querySelector('[data-act="down"]');
    if(downBtn) downBtn.addEventListener('click', ()=>sendFeedback(idx, 'down', downBtn));
  }
  inner.appendChild(row);
}
function sendFeedback(idx, rating, btn){
  const session = currentSession(); if(!session) return;
  const userMsg = session.messages.slice(0,idx).reverse().find(message=>message.role==='user');
  if(!userMsg || btn.dataset.pending==='true') return;
  const row = btn.closest('.msg-actions');
  const controls = row ? [...row.querySelectorAll('[data-act="up"],[data-act="down"]')] : [btn];
  controls.forEach(control=>{control.disabled=true;});
  btn.dataset.pending='true';
  btn.textContent='Sending…';
  apiPost('/api/feedback', { question: userMsg.content, rating }).then(()=>{
    delete btn.dataset.pending;
    btn.classList.add('active');
    btn.textContent = rating==='up' ? 'Thanks!' : 'Noted';
  }).catch(()=>{
    delete btn.dataset.pending;
    controls.forEach(control=>{control.disabled=false;});
    btn.textContent='Retry';
    btn.title='Feedback could not be sent. Try again.';
  });
}
async function copyMessageContent(button, content){
  const original=button.textContent;
  try{
    if(navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(content);
    }else{
      const area=document.createElement('textarea');
      area.value=content;
      area.setAttribute('readonly','');
      area.style.position='fixed';
      area.style.opacity='0';
      document.body.appendChild(area);
      area.select();
      const copied=document.execCommand('copy');
      area.remove();
      if(!copied) throw new Error('Clipboard unavailable');
    }
    button.textContent='Copied';
  }catch(error){
    button.textContent='Copy failed';
  }
  window.setTimeout(()=>{if(button.isConnected) button.textContent=original;},1800);
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
const COMPOSER_PLACEHOLDER = 'Message Zariya…  اردو میں بھی لکھیں';
const COMPOSER_PLACEHOLDER_NARROW = 'Message Zariya…';
const narrowComposerQuery = window.matchMedia('(max-width: 560px)');
function syncComposerPlaceholder(){ input.placeholder = narrowComposerQuery.matches ? COMPOSER_PLACEHOLDER_NARROW : COMPOSER_PLACEHOLDER; }
syncComposerPlaceholder();
if(narrowComposerQuery.addEventListener) narrowComposerQuery.addEventListener('change', syncComposerPlaceholder);
const sendBtn = document.getElementById('sendBtn');
const SEND_ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
const STOP_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>';
function syncSendState(){ if(isGenerating) return; sendBtn.disabled = input.value.trim().length===0 || shouldListen; }
input.addEventListener('input', ()=>{
  syncUrduInput(input);
  input.style.height='auto';
  input.style.height=Math.min(input.scrollHeight,160)+'px';
  syncSendState();
});
syncUrduInput(input);
input.addEventListener('keydown', (e)=>{ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); if(!sendBtn.disabled) sendMessage(); } });
sendBtn.addEventListener('click', ()=>{ if(sendBtn.dataset.mode==='stop'){ stopGenerating(); } else if(!sendBtn.disabled){ sendMessage(); } });
syncSendState();

function sendMessage(){
  if(voiceState==='recording'){
    stopVoiceRecognition();
    return;
  }
  if(voiceState==='starting'||voiceState==='transcribing'){
    showVoiceHint('Please wait until the recording has finished transcribing.');
    return;
  }
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
  updateQuickToolsState();
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
  const generation={
    id:++generationSequence,
    controller:new AbortController(),
    session,
    reply:'',
    stopped:false,
    partialSaved:false
  };
  activeGeneration=generation;
  setGenerating(true);
  showThinking();
  let reply='';
  let bubbleEl=null;
  let streamError='';
  const handleStreamPayload = payload=>{
    if(payload.error){ streamError=String(payload.error); return; }
    if(generation.stopped) return;
    if(payload.reset){
      reply='';
      generation.reply='';
      if(bubbleEl) updateStreamingBubble(bubbleEl,reply);
    }
    if(payload.notice){
      const hint=document.getElementById('composerHint');
      if(hint) hint.textContent=payload.notice;
    }
    if(payload.delta){
      reply+=payload.delta;
      generation.reply=reply;
      if(!bubbleEl){ removeThinking(); bubbleEl=appendStreamingBubble(); }
      updateStreamingBubble(bubbleEl,reply);
    }
    if(payload.done && payload.provider==='knowledge'){
      const hint=document.getElementById('composerHint');
      if(hint) hint.textContent='Using Zariya’s built-in knowledge mode. Some questions need the hosted model.';
    }
  };
  try{
    if(!window.ZariyaSSE || typeof window.ZariyaSSE.consume!=='function'){
      throw new Error('The chat stream parser did not load. Refresh the page and try again.');
    }
    const res=await fetch('/api/chat/stream',{
      method:'POST',
      headers:{'Content-Type':'application/json','Accept':'text/event-stream'},
      body:JSON.stringify({
        messages:session.messages.map(message=>({role:message.role,content:message.content})),
        systemPrompt:[responseStylePresets[genPrefs.responseStyle||'balanced']?.instruction,genPrefs.persona].filter(Boolean).join('\n\n') || undefined,
        temperature:typeof genPrefs.temperature==='number' ? genPrefs.temperature : undefined
      }),
      signal:generation.controller.signal
    });
    if(!res.ok || !res.body){
      let data={};
      try{ data=await res.json(); }catch(error){}
      throw new Error(data.error || 'The free AI service returned an error.');
    }
    const reader=res.body.getReader();
    const decoder=new TextDecoder();
    let buffer='';
    while(true){
      const {done,value}=await reader.read();
      if(done) break;
      buffer+=decoder.decode(value,{stream:true});
      buffer=window.ZariyaSSE.consume(buffer,handleStreamPayload);
    }
    buffer+=decoder.decode();
    window.ZariyaSSE.consume(buffer,handleStreamPayload,true);
    if(streamError) throw new Error(streamError);
  }catch(error){
    if(error.name==='AbortError' || generation.stopped){
      if(generation.stopped && generation.reply.trim() && !generation.partialSaved){
        session.messages.push({role:'assistant',content:generation.reply,ts:nowISO()});
        generation.partialSaved=true;
        saveServerState();
      }
      if(activeGeneration===generation){
        activeGeneration=null;
        removeThinking();
        setGenerating(false);
        if(currentSessionId===session.id) renderChat();
      }
      return;
    }
    if(reply.trim()){
      reply += '\n\n---\n\n*The connection stopped before the full answer arrived. This is the partial response received so far.*';
    }else{
      reply='Free AI is temporarily unavailable: '+(error.message || 'Please try again shortly.');
      const hint=document.getElementById('composerHint');
      if(hint) hint.textContent='Free AI is busy or unavailable. Your message is saved; try again shortly.';
    }
  }
  if(generation.stopped) return;
  if(activeGeneration===generation){
    activeGeneration=null;
    removeThinking();
    setGenerating(false);
  }
  if(!reply) reply='I couldn’t generate a response. Please try again.';
  session.messages.push({role:'assistant',content:reply,ts:nowISO()});
  saveServerState();
  if(currentSessionId===session.id) renderChat();
  if(uiPrefs.ttsEnabled) speak(reply);
}

function appendStreamingBubble(){
  const inner = document.getElementById('chat-inner');
  const scroll = document.getElementById('chat-scroll');
  scroll.classList.remove('empty-mode'); inner.classList.remove('empty-mode');
  const row = document.createElement('div');
  row.className = 'msg-row assistant';
  row.innerHTML = '<img class="avatar-logo" src="/static/logo.png" alt=""><div class="bubble-col assistant-col"><div class="bubble assistant" id="streamingBubbleContent" dir="auto"></div></div>';
  inner.appendChild(row);
  scroll.scrollTop = 999999;
  return row.querySelector('#streamingBubbleContent');
}
function updateStreamingBubble(el, text){
  el.innerHTML = renderMarkdown(text);
  el.classList.toggle('is-urdu', isPureUrdu(text));
  el.setAttribute('dir','auto');
  document.getElementById('chat-scroll').scrollTop = 999999;
}
function stopGenerating(){
  const generation=activeGeneration;
  if(!generation) return;
  generation.stopped=true;
  if(generation.reply.trim() && !generation.partialSaved){
    generation.session.messages.push({role:'assistant',content:generation.reply,ts:nowISO()});
    generation.partialSaved=true;
    saveServerState();
  }
  activeGeneration=null;
  generation.controller.abort();
  removeThinking();
  setGenerating(false);
  if(currentSessionId===generation.session.id) renderChat();
}
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
function updateQuickToolsState(){
  const session=currentSession();
  const ready=!!(session && session.messages.length) && !isGenerating && !isQuickToolBusy;
  document.querySelectorAll('.qt-btn').forEach(button=>{
    button.disabled=!ready;
    button.title=ready ? '' : (isGenerating || isQuickToolBusy ? 'Wait for the current action to finish.' : 'Start a chat before using this tool.');
  });
}
async function runQuickTool(tool){
  if(isGenerating || isQuickToolBusy) return;
  const session = currentSession();
  if(!session || !session.messages.length){
    const hint=document.getElementById('composerHint');
    if(hint) hint.textContent='Start a chat and send a message before using these tools.';
    updateQuickToolsState();
    return;
  }
  const payload = { messages: session.messages.map(m=>({role:m.role, content:m.content})) };
  const button=document.querySelector('.qt-btn[data-tool="'+tool+'"]');
  const originalLabel=button ? button.textContent : '';
  isQuickToolBusy=true;
  if(button) button.textContent='Working…';
  updateQuickToolsState();
  try{
    if(tool==='summarize'){
      const {result} = await apiPost('/api/tools/summarize', payload);
      session.messages.push({role:'assistant', content:'**Conversation summary**\n\n'+result, ts:nowISO()});
    } else if(tool==='keypoints'){
      const {result} = await apiPost('/api/tools/keypoints', payload);
      session.messages.push({role:'assistant', content:'**Key points**\n\n'+result, ts:nowISO()});
    } else if(tool==='translate'){
      const {result} = await apiPost('/api/tools/translate', payload);
      session.messages.push({role:'assistant', content:'**Translation**\n\n'+result, ts:nowISO()});
    } else if(tool==='flashcards'){
      const {cards} = await apiPost('/api/tools/flashcards', payload);
      if(cards && cards.length){
        const deck = {id:uid(), name:session.title+' - flashcards', tags:[], cards:cards.map(c=>migrateCardForSpacedRepetition({id:uid(),front:c.front,back:c.back,known:false})), createdAt:Date.now()};
        decks.unshift(deck); saveServerState();
        switchView('flashcards'); renderDeckGrid(); openDeck(deck.id);
        return;
      }
      session.messages.push({role:'assistant',content:'Not enough content yet to build flashcards.',ts:nowISO()});
    } else if(tool==='websearch'){
      const lastUser=[...session.messages].reverse().find(m=>m.role==='user');
      if(!lastUser) return;
      showThinking();
      const res=await apiPost('/api/search',{query:lastUser.content});
      removeThinking();
      if(!res.results || !res.results.length){
        session.messages.push({role:'assistant',content:'No web results came back for that search.',ts:nowISO()});
      } else {
        const body=res.results.map((r,i)=>(i+1)+'. '+r.title+'\n'+r.link+'\n'+r.snippet).join('\n\n');
        session.messages.push({
          role:'assistant',
          content:'Web search results for "'+lastUser.content+'":\n\n'+body,
          html:renderSearchResultsHtml(lastUser.content,res.results),
          ts:nowISO()
        });
      }
    } else if(tool==='title'){
      session.title=session.messages.find(m=>m.role==='user')?.content.slice(0,42)||session.title;
      saveServerState(); renderSessionList();
      return;
    } else if(tool==='exportchat'){
      const lines=session.messages.map(m=>(m.role==='user'?'**You:** ':'**Zariya:** ')+m.content);
      const filename=(session.title||'chat').replace(/[^\w\- ]/g,'').trim().replace(/\s+/g,'_')+'.md';
      downloadFile(filename,'# '+session.title+'\n\n'+lines.join('\n\n'));
      return;
    }
    saveServerState();
    if(currentSessionId===session.id) renderChat();
  }catch(err){
    removeThinking();
    session.messages.push({role:'assistant',content:'That tool is not available right now: '+(err.message||'request failed'),ts:nowISO()});
    saveServerState();
    if(currentSessionId===session.id) renderChat();
  }finally{
    isQuickToolBusy=false;
    if(button) button.textContent=originalLabel;
    updateQuickToolsState();
  }
}

/* ============ SPEECH ============ */
function speechPlainText(value){
  return String(value||'')
    .replace(new RegExp('(?:\\u0060){3}[\\s\\S]*?(?:\\u0060){3}','g'),' Code block omitted. ')
    .replace(new RegExp('\\u0060([^\\u0060]+)\\u0060','g'),'$1')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g,'$1')
    .replace(/\[([^\]]+)\]\((?:https?:\/\/)[^)]+\)/g,'$1')
    .replace(/https?:\/\/\S+/g,'')
    .replace(/^#{1,6}\s*/gm,'')
    .replace(/^\s*[-*+]\s+/gm,'')
    .replace(/^\s*\d+\.\s+/gm,'')
    .replace(/\*\*(.*?)\*\*/g,'$1')
    .replace(/~~(.*?)~~/g,'$1')
    .replace(/\*(.*?)\*/g,'$1')
    .replace(/_([^_]+)_/g,'$1')
    .replace(/^\s*\|?[\s:|-]+\|?\s*$/gm,'')
    .replace(/[|]/g,' ')
    .replace(/\n{3,}/g,'\n\n')
    .trim();
}
function speak(text){
  if(!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance==='undefined') return false;
  const readable=speechPlainText(text);
  if(!readable) return false;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(readable);
  u.lang = isUrdu(text) ? 'ur-PK' : 'en-US';
  const voices = window.speechSynthesis.getVoices();
  const match = voices.find(v=>v.lang.toLowerCase()===u.lang.toLowerCase()) || voices.find(v=>v.lang.toLowerCase().startsWith(u.lang.slice(0,2)));
  if(match) u.voice = match;
  window.speechSynthesis.speak(u);
  return true;
}

const micBtn = document.getElementById('micBtn');
const voiceLanguage = document.getElementById('voiceLanguage');
const composerHint = document.getElementById('composerHint');
const composerBox = document.getElementById('composerBox');
const voiceDropdown = document.getElementById('voiceDropdown');
const voiceDropdownTrigger = document.getElementById('voiceDropdownTrigger');
const voiceDropdownLabel = document.getElementById('voiceDropdownLabel');
const voiceDropdownMenu = document.getElementById('voiceDropdownMenu');
const voiceOptions = [...document.querySelectorAll('[data-language]')];
const AudioContextClass = window.AudioContext || window.webkitAudioContext;
let listening = false;
let recordingStream = null;
let recordingContext = null;
let recordingSource = null;
let recordingProcessor = null;
let recordingMute = null;
let recordingChunks = [];
let recordingFrames = 0;
let recordingSampleRate = 0;
let recordingTimer = null;
const MAX_VOICE_SECONDS = 60;
const savedVoiceLanguage = LS.get('zariya_voice_language', 'auto');
const initialVoiceLanguage = savedVoiceLanguage === 'en-US' ? 'en' : savedVoiceLanguage === 'ur-PK' ? 'ur' : ['en','ur'].includes(savedVoiceLanguage) ? savedVoiceLanguage : 'auto';

function showVoiceHint(message, mode='idle'){
  composerHint.textContent = message;
  composerHint.classList.toggle('listening', mode==='recording');
  composerHint.classList.toggle('transcribing', mode==='transcribing');
}
function voiceLanguageName(value){
  return value==='en' ? 'English' : value==='ur' ? 'Urdu' : 'Auto';
}
function setVoiceDropdownOpen(open){
  voiceDropdown.classList.toggle('open',open);
  voiceDropdownMenu.hidden=!open;
  voiceDropdownTrigger.setAttribute('aria-expanded',String(open));
}
function setVoiceLanguage(value){
  if(!['auto','en','ur'].includes(value)) value='auto';
  if(voiceState!=='idle') return;
  voiceLanguage.value=value;
  LS.set('zariya_voice_language',value);
  voiceDropdownLabel.textContent=value==='ur'?'اردو':value.toUpperCase();
  voiceDropdownTrigger.setAttribute('aria-label','Transcription language: '+voiceLanguageName(value));
  voiceOptions.forEach(option=>{
    option.setAttribute('aria-selected',String(option.dataset.language===value));
  });
  setVoiceDropdownOpen(false);
}
setVoiceLanguage(initialVoiceLanguage);
voiceDropdownTrigger.addEventListener('click',()=>{
  setVoiceDropdownOpen(voiceDropdownMenu.hidden);
});
voiceOptions.forEach((option,index)=>{
  option.addEventListener('click',()=>setVoiceLanguage(option.dataset.language));
  option.addEventListener('keydown',event=>{
    if(event.key==='Escape'){
      event.preventDefault();setVoiceDropdownOpen(false);voiceDropdownTrigger.focus();
    }else if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();
      const direction=event.key==='ArrowDown'?1:-1;
      voiceOptions[(index+direction+voiceOptions.length)%voiceOptions.length].focus();
    }else if(event.key==='Home'||event.key==='End'){
      event.preventDefault();voiceOptions[event.key==='Home'?0:voiceOptions.length-1].focus();
    }
  });
});
voiceDropdownTrigger.addEventListener('keydown',event=>{
  if(event.key==='ArrowDown'||event.key==='Enter'||event.key===' '){
    event.preventDefault();setVoiceDropdownOpen(true);voiceOptions[0].focus();
  }else if(event.key==='Escape'){
    setVoiceDropdownOpen(false);
  }
});
document.addEventListener('pointerdown',event=>{
  if(!voiceDropdown.contains(event.target)) setVoiceDropdownOpen(false);
});

function encodeWav(samples,sampleRate){
  const targetRate=16000;
  const ratio=sampleRate/targetRate;
  const targetLength=Math.floor(samples.length/ratio);
  const bytesPerSample=2;
  const buffer=new ArrayBuffer(44+targetLength*bytesPerSample);
  const view=new DataView(buffer);
  const writeString=(offset,value)=>{for(let i=0;i<value.length;i++) view.setUint8(offset+i,value.charCodeAt(i));};
  writeString(0,'RIFF');
  view.setUint32(4,36+targetLength*bytesPerSample,true);
  writeString(8,'WAVE');
  writeString(12,'fmt ');
  view.setUint32(16,16,true);
  view.setUint16(20,1,true);
  view.setUint16(22,1,true);
  view.setUint32(24,targetRate,true);
  view.setUint32(28,targetRate*bytesPerSample,true);
  view.setUint16(32,bytesPerSample,true);
  view.setUint16(34,16,true);
  writeString(36,'data');
  view.setUint32(40,targetLength*bytesPerSample,true);
  let offset=44;
  for(let i=0;i<targetLength;i++){
    const position=i*ratio;
    const left=Math.floor(position);
    const fraction=position-left;
    const first=samples[Math.min(left,samples.length-1)]||0;
    const second=samples[Math.min(left+1,samples.length-1)]||0;
    const sample=Math.max(-1,Math.min(1,first+(second-first)*fraction));
    view.setInt16(offset,sample<0?sample*0x8000:sample*0x7fff,true);
    offset+=bytesPerSample;
  }
  return new Blob([buffer],{type:'audio/wav'});
}
function cleanupVoiceCapture(){
  if(recordingTimer){clearTimeout(recordingTimer);recordingTimer=null;}
  if(recordingProcessor){
    recordingProcessor.onaudioprocess=null;
    try{recordingProcessor.disconnect();}catch(error){}
    recordingProcessor=null;
  }
  if(recordingSource){try{recordingSource.disconnect();}catch(error){}recordingSource=null;}
  if(recordingMute){try{recordingMute.disconnect();}catch(error){}recordingMute=null;}
  if(recordingStream){
    recordingStream.getTracks().forEach(track=>track.stop());
    recordingStream=null;
  }
}
function resetVoiceUI(message){
  voiceState='idle';listening=false;shouldListen=false;
  micBtn.disabled=false;
  micBtn.classList.remove('active','transcribing');
  micBtn.setAttribute('aria-pressed','false');
  micBtn.setAttribute('aria-label','Start voice transcription');
  micBtn.title='Record voice, then transcribe it';
  composerBox.classList.remove('listening','transcribing');
  syncSendState();
  if(message) showVoiceHint(message);
}
async function startVoiceRecognition(){
  if(voiceState!=='idle') return;
  let pendingStreamPromise=null;
  if(!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !AudioContextClass){
    showVoiceHint('Microphone recording needs HTTPS and a browser that supports audio capture. Try the latest Chrome or Edge.');
    return;
  }
  voiceState='starting';shouldListen=true;listening=false;
  micBtn.disabled=true;
  syncSendState();
  showVoiceHint('Requesting microphone access…');
  try{
    // Start both permission and audio-context requests directly from the mic tap,
    // before yielding to an await (some browsers require this user activation).
    recordingContext=new AudioContextClass();
    pendingStreamPromise=navigator.mediaDevices.getUserMedia({
      audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}
    });
    const resumePromise=recordingContext.resume();
    const [stream]=await Promise.all([pendingStreamPromise,resumePromise]);
    pendingStreamPromise=null;
    recordingStream=stream;
    recordingSampleRate=recordingContext.sampleRate;
    recordingChunks=[];recordingFrames=0;
    recordingSource=recordingContext.createMediaStreamSource(stream);
    recordingProcessor=recordingContext.createScriptProcessor(4096,1,1);
    recordingMute=recordingContext.createGain();
    recordingMute.gain.value=0;
    recordingProcessor.onaudioprocess=event=>{
      if(voiceState!=='recording') return;
      const channel=event.inputBuffer.getChannelData(0);
      recordingChunks.push(new Float32Array(channel));
      recordingFrames+=channel.length;
    };
    recordingSource.connect(recordingProcessor);
    recordingProcessor.connect(recordingMute);
    recordingMute.connect(recordingContext.destination);
    voiceState='recording';listening=true;shouldListen=true;
    micBtn.disabled=false;
    micBtn.classList.add('active');
    micBtn.setAttribute('aria-pressed','true');
    micBtn.setAttribute('aria-label','Stop and transcribe recording');
    micBtn.title='Stop recording and transcribe';
    composerBox.classList.add('listening');
    showVoiceHint('Recording '+voiceLanguageName(voiceLanguage.value)+'… press the microphone again to transcribe.', 'recording');
    recordingTimer=setTimeout(()=>stopVoiceRecognition(),MAX_VOICE_SECONDS*1000);
  }catch(error){
    if(pendingStreamPromise){
      pendingStreamPromise.then(stream=>stream.getTracks().forEach(track=>track.stop())).catch(()=>{});
      pendingStreamPromise=null;
    }
    cleanupVoiceCapture();
    if(recordingContext){
      try{await recordingContext.close();}catch(closeError){}
      recordingContext=null;
    }
    const messages={
      NotAllowedError:'Microphone permission was blocked. Allow microphone access for this site, then try again.',
      SecurityError:'Microphone access requires HTTPS. Open Zariya using its secure website address.',
      NotFoundError:'No working microphone was found. Connect a microphone and try again.',
      NotReadableError:'The microphone is busy in another app. Close that app and try again.',
      AbortError:'Microphone access was interrupted. Please try again.'
    };
    resetVoiceUI(messages[error.name]||'Could not start microphone recording. Check the microphone permission and try again.');
  }
}
async function stopVoiceRecognition(){
  if(voiceState==='starting'||voiceState==='transcribing') return;
  if(voiceState!=='recording') return;
  voiceState='transcribing';listening=false;shouldListen=true;
  micBtn.disabled=true;
  micBtn.classList.remove('active');micBtn.classList.add('transcribing');
  micBtn.setAttribute('aria-pressed','false');
  micBtn.setAttribute('aria-label','Transcribing recording');
  micBtn.title='Transcribing recording…';
  composerBox.classList.remove('listening');composerBox.classList.add('transcribing');
  showVoiceHint('Transcribing your recording…', 'transcribing');
  const chunks=recordingChunks;
  const frameCount=recordingFrames;
  const sampleRate=recordingSampleRate;
  recordingChunks=[];recordingFrames=0;
  cleanupVoiceCapture();
  try{
    if(recordingContext){
      try{await recordingContext.close();}catch(error){}
      recordingContext=null;
    }
    if(!frameCount || frameCount/sampleRate<0.25){
      resetVoiceUI('No speech was captured. Record a slightly longer voice note and try again.');
      return;
    }
    const samples=new Float32Array(frameCount);
    let offset=0;
    chunks.forEach(chunk=>{samples.set(chunk,offset);offset+=chunk.length;});
    const wav=encodeWav(samples,sampleRate);
    if(wav.size>2_500_000){
      resetVoiceUI('That recording is too large. Keep voice notes under 60 seconds.');
      return;
    }
    const audioBase64=await new Promise((resolve,reject)=>{
      const reader=new FileReader();
      reader.onload=()=>resolve(String(reader.result||'').split(',')[1]||'');
      reader.onerror=()=>reject(new Error('Could not prepare the recording. Please try again.'));
      reader.readAsDataURL(wav);
    });
    const response=await fetch('/api/transcribe',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({audio:audioBase64,mediaType:'audio/wav',language:voiceLanguage.value||'auto'})
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(data.error||'Transcription could not be completed. Please try again.');
    const transcript=String(data.text||'').trim();
    if(!transcript) throw new Error('No speech was detected. Try speaking a little closer to the microphone.');
    const existing=input.value.trim();
    input.value=existing?existing+'\n'+transcript:transcript;
    syncUrduInput(input);
    input.style.height='auto';
    input.style.height=Math.min(input.scrollHeight,160)+'px';
    syncSendState();
    resetVoiceUI('Transcript ready. Review it, then press send.');
    input.focus();
  }catch(error){
    resetVoiceUI(error.message||'Transcription failed. Please try again.');
  }
}
micBtn.addEventListener('click',()=>{
  if(voiceState==='recording') stopVoiceRecognition();
  else if(voiceState==='idle') startVoiceRecognition();
});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden&&voiceState==='recording') stopVoiceRecognition();
});
window.addEventListener('pagehide',()=>{
  if(voiceState==='recording'){
    cleanupVoiceCapture();
    voiceState='idle';listening=false;shouldListen=false;
  }
});

/* ============ NOTEPAD ============ */
function updateNoteActionState(){
  const note=notes.find(item=>item.id===currentNoteId);
  const hasNote=!!note;
  const hasBody=hasNote && !!document.getElementById('note-body-input').value.trim();
  document.getElementById('exportNoteBtn').disabled=!hasNote;
  document.getElementById('deleteNoteBtn').disabled=!hasNote;
  document.getElementById('noteToFlashBtn').disabled=!hasBody;
}
function setNoteSaveStatus(message,warning=false){
  const status=document.getElementById('noteSaveStatus');
  if(!status) return;
  status.textContent=message;
  status.classList.toggle('warning',!!warning);
}
function syncNoteEditorState(){
  const note=notes.find(n=>n.id===currentNoteId);
  const hasNote=!!note;
  const editor=document.querySelector('.note-editor');
  const emptyState=document.getElementById('noteEmptyState');
  const fields=document.getElementById('noteEditorFields');
  if(editor) editor.classList.toggle('is-empty',!hasNote);
  if(emptyState) emptyState.hidden=hasNote;
  if(fields) fields.hidden=!hasNote;
  if(note){
    document.getElementById('note-title-input').value=note.title||'';
    document.getElementById('note-body-input').value=note.body||'';
    document.getElementById('note-tags-input').value=(note.tags||[]).join(', ');
  }else{
    document.getElementById('note-title-input').value='';
    document.getElementById('note-body-input').value='';
    document.getElementById('note-tags-input').value='';
  }
  syncUrduInput(document.getElementById('note-title-input'));
  syncUrduInput(document.getElementById('note-body-input'));
  syncUrduInput(document.getElementById('note-tags-input'));
}
function renderNotesList(){
  const wrap = document.getElementById('notesList'); wrap.innerHTML='';
  renderNoteTagFilterRow();
  const visibleNotes = activeNoteTagFilter ? notes.filter(n=>(n.tags||[]).includes(activeNoteTagFilter)) : notes;
  if(!visibleNotes.length){
    wrap.innerHTML = '<div class="empty-mini"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg><span>'+(activeNoteTagFilter?'No notes with this tag':'No notes yet')+'</span></div>';
  }
  visibleNotes.forEach(n=>{
    const div = document.createElement('div');
    div.className = 'note-card'+(n.id===currentNoteId?' active':'');
    div.innerHTML = '<div class="note-card-title" dir="auto">'+wrapUrduRuns(escapeHtml(n.title||'Untitled'))+'</div><div class="note-card-preview" dir="auto">'+wrapUrduRuns(escapeHtml((n.body||'').slice(0,60)))+'</div>'+((n.tags&&n.tags.length)?'<div class="note-card-tags">'+n.tags.map(t=>'<span>'+wrapUrduRuns(escapeHtml(t))+'</span>').join('')+'</div>':'');
    div.addEventListener('click', ()=>openNote(n.id));
    wrap.appendChild(div);
  });
  const previousNoteId=currentNoteId;
  if(!visibleNotes.some(n=>n.id===currentNoteId)){
    currentNoteId=visibleNotes.length ? visibleNotes[0].id : null;
  }
  syncNoteEditorState();
  if(previousNoteId!==currentNoteId){
    setNoteSaveStatus(currentNoteId?'Saved on this device':'');
  }
  updateNoteActionState();
}
  function renderNoteTagFilterRow(){
      const row = document.getElementById('noteTagFilterRow');
      if(!row) return;
      const tagCounts = {};
      notes.forEach(n=>(n.tags||[]).forEach(t=>{ tagCounts[t] = (tagCounts[t]||0)+1; }));
      const tags = Object.keys(tagCounts).sort();
      if(!tags.length){ row.innerHTML = ''; return; }
      row.innerHTML = tags.map(t=>'<button type="button" class="tag-chip'+(activeNoteTagFilter===t?' active':'')+'" data-tag="'+escapeHtml(t)+'" aria-pressed="'+(activeNoteTagFilter===t)+'">'+escapeHtml(t)+' ('+tagCounts[t]+')</button>').join('');
      row.querySelectorAll('.tag-chip').forEach(chip=>{
            chip.addEventListener('click', ()=>{
                    const t = chip.dataset.tag;
                    activeNoteTagFilter = activeNoteTagFilter===t ? null : t;
                    renderNotesList();
            });
      });
  }
function openNote(id){
  const changed=currentNoteId!==id;
  currentNoteId = id;
  const n = notes.find(n=>n.id===id);
  if(changed) setNoteSaveStatus('Saved on this device');
  document.getElementById('note-title-input').value = n? n.title : '';
  document.getElementById('note-body-input').value = n? n.body : '';
  document.getElementById('note-tags-input').value = n && n.tags ? n.tags.join(', ') : '';
  syncUrduInput(document.getElementById('note-title-input'));
  syncUrduInput(document.getElementById('note-body-input'));
  syncUrduInput(document.getElementById('note-tags-input'));
  renderNotesList();
}
document.getElementById('newNoteBtn').addEventListener('click', ()=>{
  const n = {id:uid(), title:'Untitled note', body:'', tags:[], updatedAt:Date.now()};
  notes.unshift(n);
  currentNoteId=null;
  activeNoteTagFilter=null;
  saveServerState();
  openNote(n.id);
  document.getElementById('note-title-input').focus();
});
document.getElementById('createFirstNoteBtn').addEventListener('click', ()=>{
  document.getElementById('newNoteBtn').click();
});
document.getElementById('deleteNoteBtn').addEventListener('click', ()=>{
  if(!currentNoteId) return;
  const n = notes.find(n=>n.id===currentNoteId);
  if(!confirm('Delete "'+((n&&n.title)||'this note')+'"? This cannot be undone.')) return;
  notes = notes.filter(n=>n.id!==currentNoteId);
  currentNoteId = null;
  activeNoteTagFilter = null;
  saveServerState();
  renderNotesList();
});
let noteTitleSaveTimer, noteBodySaveTimer;
document.getElementById('note-title-input').addEventListener('input', ()=>{
  syncUrduInput(document.getElementById('note-title-input'));
  setNoteSaveStatus('Unsaved changes');
  clearTimeout(noteTitleSaveTimer);
  noteTitleSaveTimer = setTimeout(()=>{
    const n=notes.find(n=>n.id===currentNoteId);
    if(n){
      n.title=document.getElementById('note-title-input').value||'Untitled note';
      const saved=saveServerState();
      setNoteSaveStatus(saved===false?'Could not save':'Saved just now',saved===false);
      renderNotesList();
    }
  },400);
});
document.getElementById('note-body-input').addEventListener('input', ()=>{
  syncUrduInput(document.getElementById('note-body-input'));
  updateNoteActionState();
  setNoteSaveStatus('Unsaved changes');
  clearTimeout(noteBodySaveTimer);
  noteBodySaveTimer = setTimeout(()=>{
    const n=notes.find(n=>n.id===currentNoteId);
    if(n){
      n.body=document.getElementById('note-body-input').value;
      const saved=saveServerState();
      setNoteSaveStatus(saved===false?'Could not save':'Saved just now',saved===false);
      renderNotesList();
    }
  },400);
});
document.getElementById('exportNoteBtn').addEventListener('click', ()=>{
  const n = notes.find(n=>n.id===currentNoteId); if(!n) return;
  const filename=(n.title||'note').replace(/[^\w\- ]/g,'').trim().replace(/\s+/g,'_') || 'note';
  downloadFile(filename+'.md', '# '+n.title+'\n\n'+n.body,'text/markdown;charset=utf-8');
});
  let noteTagsSaveTimer;
  document.getElementById('note-tags-input').addEventListener('input', ()=>{
      syncUrduInput(document.getElementById('note-tags-input'));
      setNoteSaveStatus('Unsaved changes');
      clearTimeout(noteTagsSaveTimer);
      noteTagsSaveTimer = setTimeout(()=>{
            const n = notes.find(n=>n.id===currentNoteId);
            if(n){
                    n.tags = document.getElementById('note-tags-input').value.split(',').map(t=>t.trim().toLowerCase()).filter(Boolean);
                    const saved=saveServerState();
                    setNoteSaveStatus(saved===false?'Could not save':'Saved just now',saved===false);
                    renderNotesList();
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
  if(!c.id) c.id = uid();
  if(c.due === undefined || !Number.isFinite(Date.parse(c.due))) c.due = new Date(0).toISOString();
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
  if(!visibleDecks.length){
    const empty=document.createElement('div');
    empty.className='empty-mini deck-empty';
    empty.innerHTML='<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="6" width="16" height="12" rx="2"/><path d="M6 2h16v12"/></svg><strong>Your first deck starts here</strong><span>Create a deck yourself, or ask Zariya to turn a chat into flashcards.</span><button class="btn primary" type="button">Create first deck</button>';
    const action=empty.querySelector('button');
    action.addEventListener('click',()=>{
      if(activeDeckTagFilter){
        activeDeckTagFilter=null;
        renderDeckGrid();
      }else{
        document.getElementById('newDeckBtn').click();
      }
    });
    if(activeDeckTagFilter) action.textContent='Clear filter';
    grid.appendChild(empty);
    return;
  }
  visibleDecks.forEach(d=>{
    d.cards.forEach(migrateCardForSpacedRepetition);
    const known = d.cards.filter(c=>c.known).length;
    const pct = d.cards.length? Math.round(known/d.cards.length*100):0;
    const due = cardsDue(d.cards).length;
    const card = document.createElement('div'); card.className='deck-card';
    card.innerHTML = '<h3>'+escapeHtml(d.name)+'</h3><p>'+d.cards.length+' card'+(d.cards.length!==1?'s':'')+' · '+pct+'% known'+(due? ' · <strong style="color:var(--accent-strong);">'+due+' due</strong>':' · none due')+'</p><div class="deck-progress"><div class="deck-progress-fill" style="width:'+pct+'%"></div></div>'+
        '<div class="deck-card-tags">'+((d.tags&&d.tags.length)?d.tags.map(t=>'<span>'+escapeHtml(t)+'</span>').join(''):'')+'</div>'+
      '<div class="deck-card-actions"><button class="deck-action-btn" data-action="study">Study</button><button class="deck-action-btn" data-action="quiz"'+(d.cards.length<2?' disabled title="Needs at least 2 cards"':'')+'>Quiz</button><button class="deck-action-btn" data-action="edit" title="Edit cards" aria-label="Edit deck cards">Edit</button><button class="deck-action-btn" data-action="rename" title="Rename deck" aria-label="Rename deck">Rename</button><button class="deck-action-btn" data-action="export" title="Download as JSON">Export</button><button class="deck-action-btn danger" data-action="delete" title="Delete deck" aria-label="Delete deck">Delete</button></div>';
    card.querySelector('[data-action="study"]').addEventListener('click', (e)=>{ e.stopPropagation(); openDeck(d.id); });
    const quizBtn = card.querySelector('[data-action="quiz"]');
    quizBtn.addEventListener('click', (e)=>{ e.stopPropagation(); if(!quizBtn.disabled) startQuiz(d.id); });
    card.querySelector('[data-action="edit"]').addEventListener('click', (e)=>{ e.stopPropagation(); editDeck(d.id); });
    card.querySelector('[data-action="export"]').addEventListener('click', (e)=>{ e.stopPropagation(); exportDeck(d); });
    card.querySelector('[data-action="rename"]').addEventListener('click', (e)=>{ e.stopPropagation(); renameDeck(d.id); });
    card.querySelector('[data-action="delete"]').addEventListener('click', (e)=>{ e.stopPropagation(); deleteDeck(d.id); });
    card.addEventListener('click', ()=>openDeck(d.id));
    grid.appendChild(card);
  });
}
function editDeck(id){
  const deck = decks.find(d=>d.id===id);
  if(!deck) return;
  editingDeckId = id;
  resetDeckDialog('edit');
  document.getElementById('newDeckName').value = deck.name || '';
  document.getElementById('newDeckTags').value = (deck.tags||[]).join(', ');
  deck.cards.forEach(card=>addDeckCardRow(card.front,card.back,card));
  if(newDeckDialog && typeof newDeckDialog.showModal==='function') newDeckDialog.showModal();
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
  downloadFile(deck.name.replace(/[^\w\- ]/g, '').trim().replace(/\s+/g, '_') + '.json', JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
}
function importDeckFromJson(text){
  let parsed;
  try { parsed = JSON.parse(text); } catch(e){ alert('That file is not valid JSON.'); return; }
  const sourceIsArray=Array.isArray(parsed);
  const cardsSource = sourceIsArray ? parsed : (parsed && typeof parsed==='object' ? parsed.cards : null);
  const name = !sourceIsArray && parsed && typeof parsed.name==='string'
    ? parsed.name.slice(0,100) : 'Imported deck';
  if(!Array.isArray(cardsSource) || !cardsSource.length){ alert('No cards found in that file.'); return; }
  const cards = [];
  for(const c of cardsSource.slice(0,30)){
    if(!c || typeof c.front !== 'string' || typeof c.back !== 'string') continue;
    const due=typeof c.due==='string' && Number.isFinite(Date.parse(c.due)) ? c.due : new Date(0).toISOString();
    const ease=Number(c.ease), interval=Number(c.interval), reps=Number(c.reps);
    cards.push(migrateCardForSpacedRepetition({
      id: uid(),
      front:c.front.slice(0,600),
      back:c.back.slice(0,2400),
      known:!!c.known,
      ease:Number.isFinite(ease) ? Math.min(4,Math.max(1.3,ease)) : 2.5,
      interval:Number.isFinite(interval) ? Math.max(0,Math.min(36500,interval)) : 0,
      reps:Number.isFinite(reps) ? Math.max(0,Math.min(100000,reps)) : 0,
      due
    }));
  }
  if(!cards.length){ alert('No valid cards (each needs a front and back) found in that file.'); return; }
  const tags = !sourceIsArray && parsed && Array.isArray(parsed.tags)
    ? parsed.tags.filter(tag=>typeof tag==='string').slice(0,12).map(tag=>tag.trim().toLowerCase().slice(0,40))
    : [];
  decks.unshift({ id: uid(), name, tags, cards, createdAt: Date.now() });
  saveServerState(); renderDeckGrid();
}
document.getElementById('importDeckBtn').addEventListener('click', ()=>document.getElementById('importDeckFile').click());
document.getElementById('importDeckFile').addEventListener('change', (e)=>{
  const file = e.target.files[0]; if(!file) return;
  if(file.size>5*1024*1024){ alert('That deck file is larger than 5 MB.'); e.target.value=''; return; }
  const reader = new FileReader();
  reader.onload = ()=>importDeckFromJson(String(reader.result||''));
  reader.onerror = ()=>alert('The deck file could not be read.');
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
    '<div class="flip-face front '+(isPureUrdu(c.front)?'is-urdu urdu':'')+'" dir="auto">'+wrapUrduRuns(escapeHtml(c.front))+'</div>'+
    '<div class="flip-face back '+(isPureUrdu(c.back)?'is-urdu urdu':'')+'" dir="auto">'+wrapUrduRuns(escapeHtml(c.back))+'</div></div></div>'+
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
const newDeckDialog = document.getElementById('newDeckDialog');
const newDeckCards = document.getElementById('newDeckCards');
function addDeckCardRow(front='', back='', existingCard=null){
  const count=newDeckCards.querySelectorAll('.deck-form-card').length+1;
  const row=document.createElement('div');
  row.className='deck-form-card';
  if(existingCard && existingCard.id) row.dataset.cardId=existingCard.id;
  row.innerHTML='<div class="deck-form-card-head"><span>Card '+count+'</span><button class="deck-form-remove" type="button" aria-label="Remove card">Remove</button></div>'
    +'<label>Front<input class="deck-front" maxlength="600" required placeholder="Question or term" dir="auto" value="'+escapeHtml(front)+'"></label>'
    +'<label>Back<textarea class="deck-back" maxlength="2400" required rows="2" placeholder="Answer or definition" dir="auto">'+escapeHtml(back)+'</textarea></label>';
  row.querySelector('.deck-form-remove').addEventListener('click',()=>{
    row.remove();
    newDeckCards.querySelectorAll('.deck-form-card-head span').forEach((el,i)=>el.textContent='Card '+(i+1));
  });
  const frontInput=row.querySelector('.deck-front');
  const backInput=row.querySelector('.deck-back');
  frontInput.addEventListener('input',()=>syncUrduInput(frontInput));
  backInput.addEventListener('input',()=>syncUrduInput(backInput));
  newDeckCards.appendChild(row);
  syncUrduInput(frontInput);
  syncUrduInput(backInput);
}
function resetDeckDialog(mode){
  editingDeckId = mode === 'edit' ? editingDeckId : null;
  document.getElementById('newDeckForm').reset();
  newDeckCards.innerHTML='';
  document.getElementById('newDeckFormHint').textContent='';
  document.getElementById('newDeckTitle').textContent = mode === 'edit' ? 'Edit deck' : 'Create a deck';
  document.getElementById('saveDeckBtn').textContent = mode === 'edit' ? 'Save changes' : 'Create deck';
}
document.getElementById('newDeckBtn').addEventListener('click',()=>{
  editingDeckId = null;
  resetDeckDialog('create');
  addDeckCardRow();
  if(newDeckDialog && typeof newDeckDialog.showModal==='function') newDeckDialog.showModal();
});
document.getElementById('addDeckCardBtn').addEventListener('click',()=>{
  if(newDeckCards.querySelectorAll('.deck-form-card').length>=30){
    document.getElementById('newDeckFormHint').textContent='A deck can contain up to 30 cards.';
    return;
  }
  addDeckCardRow();
});
document.getElementById('newDeckCancelBtn').addEventListener('click',()=>newDeckDialog.close());
document.getElementById('newDeckForm').addEventListener('submit',e=>{
  e.preventDefault();
  const name=document.getElementById('newDeckName').value.trim();
  const tags=document.getElementById('newDeckTags').value.split(',').map(t=>t.trim().toLowerCase()).filter(Boolean).slice(0,12);
  const existingDeck = editingDeckId ? decks.find(d=>d.id===editingDeckId) : null;
  const previousCards = new Map((existingDeck ? existingDeck.cards : []).map(card=>[card.id,card]));
  const cards=[...newDeckCards.querySelectorAll('.deck-form-card')].map(row=>{
    const previous = previousCards.get(row.dataset.cardId);
    return migrateCardForSpacedRepetition({
      ...(previous||{}),
      id: previous ? previous.id : uid(),
      front:row.querySelector('.deck-front').value.trim(),
      back:row.querySelector('.deck-back').value.trim(),
      known:previous ? !!previous.known : false
    });
  }).filter(card=>card.front&&card.back);
  if(!name||!cards.length){
    document.getElementById('newDeckFormHint').textContent='Add a deck name and at least one complete card.';
    return;
  }
  if(existingDeck){
    existingDeck.name=name;
    existingDeck.tags=tags;
    existingDeck.cards=cards;
  }else{
    decks.unshift({id:uid(),name,tags,cards,createdAt:Date.now()});
  }
  editingDeckId=null;
  saveServerState();
  renderDeckGrid();
  newDeckDialog.close();
});
function renderDeckTagFilterRow(){
    const row = document.getElementById('deckTagFilterRow');
    if(!row) return;
    const tagCounts = {};
    decks.forEach(d=>(d.tags||[]).forEach(t=>{ tagCounts[t] = (tagCounts[t]||0)+1; }));
    const tags = Object.keys(tagCounts).sort();
    if(!tags.length){ row.innerHTML = ''; return; }
    row.innerHTML = tags.map(t=>'<button type="button" class="tag-chip'+(activeDeckTagFilter===t?' active':'')+'" data-tag="'+escapeHtml(t)+'" aria-pressed="'+(activeDeckTagFilter===t)+'">'+escapeHtml(t)+' ('+tagCounts[t]+')</button>').join('');
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
    '<button class="quiz-option'+(isPureUrdu(opt)?' is-urdu urdu':'')+'" data-i="'+i+'" data-answer-index="'+i+'" aria-pressed="false" dir="auto">'+wrapUrduRuns(escapeHtml(opt))+'</button>'
  ).join('');
  area.innerHTML = '<div class="study-progress-text">Question '+(quizIndex+1)+' of '+quizQueue.length+' -- '+escapeHtml(deck.name)+' · Score: '+quizScore+'</div>'+
    '<div class="quiz-question'+(isPureUrdu(q.front)?' is-urdu urdu':'')+'" dir="auto">'+wrapUrduRuns(escapeHtml(q.front))+'</div>'+
    '<div class="quiz-options">'+optionsHtml+'</div>'+
    '<div class="quiz-feedback" id="quizFeedback" role="status" aria-live="polite"></div>'+
    '<div class="study-controls" id="quizNextRow" style="display:none;"><button class="btn primary" id="quizNext">Next question</button></div>';
  quizAnswered = false;
  area.querySelectorAll('.quiz-option').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      if(quizAnswered) return;
      quizAnswered = true;
      const chosen = q.options[parseInt(btn.dataset.i,10)];
      area.querySelectorAll('.quiz-option').forEach(b=>{
        const val = q.options[parseInt(b.dataset.i,10)];
        const isCorrect=val===q.correct;
        const isChosen=b===btn;
        if(isCorrect) b.classList.add('correct');
        else if(isChosen) b.classList.add('wrong');
        b.disabled=true;
        b.setAttribute('aria-pressed',String(isChosen));
        b.setAttribute('aria-label',isChosen
          ? (isCorrect?'Your answer, correct':'Your answer, incorrect')
          : (isCorrect?'Correct answer':'Answer option'));
      });
      const feedback=document.getElementById('quizFeedback');
      const isCorrect=chosen===q.correct;
      feedback.classList.toggle('correct',isCorrect);
      feedback.classList.toggle('wrong',!isCorrect);
      feedback.innerHTML=isCorrect
        ? 'Correct answer.'
        : 'Not quite. Correct answer: '+wrapUrduRuns(escapeHtml(q.correct));
      if(isCorrect) quizScore++;
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
const responsePresetDropdown=document.getElementById('responsePresetDropdown');
const responsePresetTrigger=document.getElementById('responsePresetTrigger');
const responsePresetMenu=document.getElementById('responsePresetMenu');
const responsePresetOptions=[...document.querySelectorAll('[data-response-style]')];
function setResponsePresetMenuOpen(open){
  responsePresetDropdown.classList.toggle('open',open);
  responsePresetMenu.hidden=!open;
  responsePresetTrigger.setAttribute('aria-expanded',String(open));
}
responsePresetTrigger.addEventListener('click',()=>{
  setResponsePresetMenuOpen(responsePresetMenu.hidden);
});
responsePresetOptions.forEach((option,index)=>{
  option.addEventListener('click',()=>{
    setResponseStyle(option.dataset.responseStyle);
    setResponsePresetMenuOpen(false);
    responsePresetTrigger.focus();
  });
  option.addEventListener('keydown',event=>{
    if(event.key==='Escape'){
      event.preventDefault();setResponsePresetMenuOpen(false);responsePresetTrigger.focus();
    }else if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();
      const direction=event.key==='ArrowDown'?1:-1;
      responsePresetOptions[(index+direction+responsePresetOptions.length)%responsePresetOptions.length].focus();
    }else if(event.key==='Home'||event.key==='End'){
      event.preventDefault();responsePresetOptions[event.key==='Home'?0:responsePresetOptions.length-1].focus();
    }
  });
});
responsePresetTrigger.addEventListener('keydown',event=>{
  if(event.key==='ArrowDown'||event.key==='Enter'||event.key===' '){
    event.preventDefault();setResponsePresetMenuOpen(true);responsePresetOptions[0].focus();
  }else if(event.key==='Escape'){
    setResponsePresetMenuOpen(false);
  }
});
document.addEventListener('pointerdown',event=>{
  if(!responsePresetDropdown.contains(event.target)) setResponsePresetMenuOpen(false);
});
document.getElementById('personaInput').addEventListener('input', (e)=>{
  syncUrduInput(e.target);
  genPrefs.persona=e.target.value;
  LS.set('zariya_gen_prefs',genPrefs);
});
document.getElementById('creativitySlider').addEventListener('input', (e)=>{ const pct=parseInt(e.target.value,10); genPrefs.temperature=pct/100; LS.set('zariya_gen_prefs',genPrefs); updateCreativityLabel(pct); });
document.getElementById('resetPersonaBtn').addEventListener('click', ()=>{
  genPrefs.persona='';
  LS.set('zariya_gen_prefs',genPrefs);
  document.getElementById('personaInput').value='';
  syncUrduInput(document.getElementById('personaInput'));
});

function downloadFile(filename, content, type='text/plain;charset=utf-8'){
  const blob = new Blob([content], {type});
  const a = document.createElement('a');
  const objectUrl = URL.createObjectURL(blob);
  a.href = objectUrl; a.download = filename; a.click();
  window.setTimeout(()=>URL.revokeObjectURL(objectUrl), 1000);
}

/* ============ INIT ============ */
(async function init(){
  await loadServerState();
  applyUiPrefs();
  applyGenPrefs();
  updateStatusPill();
  renderAccountUI();
  renderSessionList();
  renderChat();
})();


// Dynamically rendered code blocks share one delegated copy action.
document.addEventListener('click', async event=>{
  const button = event.target.closest('.code-copy-btn');
  if(!button) return;
  const code = document.getElementById(button.dataset.codeId);
  if(!code) return;
  const originalLabel = button.textContent;
  try{
    if(navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(code.textContent || '');
    }else{
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      const copied = document.execCommand('copy');
      selection.removeAllRanges();
      if(!copied) throw new Error('Clipboard unavailable');
    }
    button.textContent = 'Copied';
  }catch(error){
    button.textContent = 'Copy failed';
  }
  window.setTimeout(()=>{ if(button.isConnected) button.textContent = originalLabel; }, 1400);
});
})();
