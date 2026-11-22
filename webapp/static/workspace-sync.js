(function attachWorkspaceSync(root){
  "use strict";

  const COLLECTIONS = ["sessions", "notes", "decks"];
  const MAX_TOMBSTONES = 10000;

  function isObject(value){
    return !!value && typeof value === "object" && !Array.isArray(value);
  }

  function itemId(item){
    if(!isObject(item)) return null;
    const value = item.id;
    if(typeof value !== "string" && typeof value !== "number") return null;
    const id = String(value).trim();
    return id ? id : null;
  }

  function timestamp(item){
    if(!isObject(item)) return 0;
    const value = Number(item.updatedAt ?? item.createdAt ?? 0);
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  function uniqueTombstones(...lists){
    const byId = new Map();
    lists.flat().forEach(item=>{
      if(!isObject(item) || typeof item.id !== "string" || !item.id.trim()) return;
      const deletedAt = Number(item.deletedAt);
      if(!Number.isFinite(deletedAt) || deletedAt <= 0) return;
      const previous = byId.get(item.id);
      if(!previous || deletedAt > previous.deletedAt){
        byId.set(item.id,{id:item.id,deletedAt});
      }
    });
    return [...byId.values()]
      .sort((a,b)=>b.deletedAt-a.deletedAt)
      .slice(0,MAX_TOMBSTONES);
  }

  function empty(){
    return {
      sessions:[],
      notes:[],
      decks:[],
      _deleted:{sessions:[],notes:[],decks:[]}
    };
  }

  function normalize(raw){
    const result = empty();
    if(!isObject(raw)) return result;
    COLLECTIONS.forEach(key=>{
      result[key] = Array.isArray(raw[key])
        ? raw[key].filter(isObject).map(item=>({...item}))
        : [];
      const deleted = isObject(raw._deleted) && Array.isArray(raw._deleted[key])
        ? raw._deleted[key] : [];
      result._deleted[key] = uniqueTombstones(deleted);
    });
    return result;
  }

  function applyTombstones(items,tombstones){
    const deletedById = new Map(tombstones.map(item=>[item.id,item.deletedAt]));
    const kept = items.filter(item=>{
      const id = itemId(item);
      if(!id || !deletedById.has(id)) return true;
      return timestamp(item) > deletedById.get(id);
    });
    const liveById = new Map(kept.map(item=>[itemId(item),item]).filter(([id])=>id));
    const remaining = tombstones.filter(tombstone=>{
      const live = liveById.get(tombstone.id);
      return !live || tombstone.deletedAt >= timestamp(live);
    });
    return {items:kept,tombstones:remaining};
  }

  function merge(remote,cached){
    const server = normalize(remote);
    const local = normalize(cached);
    const result = empty();

    COLLECTIONS.forEach(key=>{
      const tombstones = uniqueTombstones(server._deleted[key],local._deleted[key]);
      const byId = new Map();
      const extras = [];

      // Keep server order as the baseline, but preserve the newest local copy.
      [server[key],local[key]].forEach(items=>{
        items.forEach(item=>{
          const id = itemId(item);
          if(!id){
            extras.push(item);
            return;
          }
          const previous = byId.get(id);
          if(!previous || timestamp(item) >= timestamp(previous)){
            byId.set(id,item);
          }
        });
      });

      const cleaned = applyTombstones([...byId.values(),...extras],tombstones);
      result[key] = cleaned.items;
      result._deleted[key] = cleaned.tombstones;
    });

    return result;
  }

  function contentSignature(item){
    const copy = {...item};
    delete copy.updatedAt;
    return JSON.stringify(copy);
  }

  function stamp(current,previous,now=Date.now()){
    const next = normalize(current);
    const prior = normalize(previous);
    const clock = Number.isFinite(Number(now)) && Number(now)>0 ? Number(now) : Date.now();

    COLLECTIONS.forEach(key=>{
      const oldById = new Map(prior[key].map(item=>[itemId(item),item]).filter(([id])=>id));
      const currentIds = new Set(next[key].map(itemId).filter(Boolean));
      const tombstoneById = new Map(uniqueTombstones(next._deleted[key],prior._deleted[key]).map(item=>[item.id,item]));

      // Make removals durable so a stale device cannot bring deleted records back.
      oldById.forEach((oldItem,id)=>{
        if(!currentIds.has(id)){
          const deletedAt = Math.max(clock,timestamp(oldItem)+1,(tombstoneById.get(id)?.deletedAt||0)+1);
          tombstoneById.set(id,{id,deletedAt});
        }
      });

      next[key] = next[key].map(item=>{
        const id = itemId(item);
        const oldItem = id ? oldById.get(id) : null;
        const suppliedTime = timestamp(item);
        const oldTime = timestamp(oldItem);
        const changed = oldItem && contentSignature(item)!==contentSignature(oldItem);
        let updatedAt = suppliedTime || oldTime || clock;

        if(oldItem && changed && suppliedTime<=oldTime){
          updatedAt = Math.max(clock,oldTime+1);
        }
        return {...item,updatedAt};
      });

      const cleaned = applyTombstones(next[key],uniqueTombstones([...tombstoneById.values()]));
      next[key] = cleaned.items;
      next._deleted[key] = cleaned.tombstones;
    });

    return next;
  }

  const api = {empty,normalize,merge,stamp};
  root.ZariyaWorkspaceSync = api;
  if(typeof module!=="undefined" && module.exports) module.exports = api;
})(typeof window!=="undefined" ? window : globalThis);
