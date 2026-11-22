(function(root){
  "use strict";
  const KEYS=["sessions","notes","decks"];
  const MAX=10000;
  const object=v=>!!v&&typeof v==="object"&&!Array.isArray(v);
  const idOf=v=>object(v)&&v.id!=null?String(v.id).trim():"";
  const timeOf=v=>{
    const n=Number(v&& (v.updatedAt??v.createdAt??0));
    return Number.isFinite(n)&&n>0?n:0;
  };
  function tombstones(...groups){
    const map=new Map();
    groups.flat().forEach(t=>{
      if(!object(t)||typeof t.id!=="string"||!t.id.trim())return;
      const at=Number(t.deletedAt);
      if(!Number.isFinite(at)||at<=0)return;
      if(!map.has(t.id)||map.get(t.id).deletedAt<at)map.set(t.id,{id:t.id,deletedAt:at});
    });
    return [...map.values()].sort((a,b)=>b.deletedAt-a.deletedAt).slice(0,MAX);
  }
  function empty(){
    return {sessions:[],notes:[],decks:[],_deleted:{sessions:[],notes:[],decks:[]}};
  }
  function normalize(raw){
    const out=empty();
    if(!object(raw))return out;
    KEYS.forEach(k=>{
      out[k]=Array.isArray(raw[k])?raw[k].filter(object).map(x=>({...x})):[];
      out._deleted[k]=tombstones(object(raw._deleted)?raw._deleted[k]:[]);
    });
    return out;
  }
  function filterDeleted(items,deleted){
    const byId=new Map(deleted.map(x=>[x.id,x.deletedAt]));
    const kept=items.filter(item=>{
      const id=idOf(item);
      return !id||!byId.has(id)||timeOf(item)>byId.get(id);
    });
    const live=new Map(kept.map(x=>[idOf(x),x]).filter(([id])=>id));
    return {
      items:kept,
      deleted:deleted.filter(x=>!live.has(x.id)||x.deletedAt>=timeOf(live.get(x.id)))
    };
  }
  function merge(remote,cached){
    const a=normalize(remote),b=normalize(cached),out=empty();
    KEYS.forEach(k=>{
      const byId=new Map(),extra=[];
      [a[k],b[k]].forEach(items=>items.forEach(item=>{
        const id=idOf(item);
        if(!id){extra.push(item);return;}
        const prev=byId.get(id);
        if(!prev||timeOf(item)>=timeOf(prev))byId.set(id,item);
      }));
      const cleaned=filterDeleted([...byId.values(),...extra],tombstones(a._deleted[k],b._deleted[k]));
      out[k]=cleaned.items;
      out._deleted[k]=cleaned.deleted;
    });
    return out;
  }
  function signature(item){
    const copy={...item};delete copy.updatedAt;return JSON.stringify(copy);
  }
  function stamp(current,previous,now=Date.now()){
    const next=normalize(current),prior=normalize(previous);
    const clock=Number.isFinite(Number(now))&&Number(now)>0?Number(now):Date.now();
    KEYS.forEach(k=>{
      const old=new Map(prior[k].map(x=>[idOf(x),x]).filter(([id])=>id));
      const currentIds=new Set(next[k].map(idOf).filter(Boolean));
      const deleted=new Map(tombstones(next._deleted[k],prior._deleted[k]).map(x=>[x.id,x]));
      old.forEach((item,id)=>{
        if(!currentIds.has(id)){
          deleted.set(id,{id,deletedAt:Math.max(clock,timeOf(item)+1,(deleted.get(id)?.deletedAt||0)+1)});
        }
      });
      next[k]=next[k].map(item=>{
        const id=idOf(item),before=id?old.get(id):null;
        const supplied=timeOf(item),previousTime=timeOf(before);
        let updatedAt=supplied||previousTime||clock;
        if(before&&signature(item)!==signature(before)&&supplied<=previousTime){
          updatedAt=Math.max(clock,previousTime+1);
        }
        return {...item,updatedAt};
      });
      const cleaned=filterDeleted(next[k],tombstones([...deleted.values()]));
      next[k]=cleaned.items;
      next._deleted[k]=cleaned.deleted;
    });
    return next;
  }
  const api={empty,normalize,merge,stamp};
  root.ZariyaWorkspaceSync=api;
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window!=="undefined"?window:globalThis);
