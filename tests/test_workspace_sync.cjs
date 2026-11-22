"use strict";
const assert=require("node:assert/strict");
const sync=require("../webapp/static/workspace-sync.js");
{
 const result=sync.merge({sessions:[{id:"c",title:"server",updatedAt:10}]},{sessions:[{id:"c",title:"offline",updatedAt:20}]});
 assert.equal(result.sessions[0].title,"offline");
}
{
 const result=sync.merge({notes:[{id:"n",body:"server",updatedAt:20}]},{notes:[{id:"n",body:"local",updatedAt:10}]});
 assert.equal(result.notes[0].body,"server");
}
{
 const result=sync.merge({sessions:[{id:"c",updatedAt:20}]},{sessions:[],_deleted:{sessions:[{id:"c",deletedAt:30}]}});
 assert.equal(result.sessions.length,0);
 assert.equal(result._deleted.sessions[0].deletedAt,30);
}
{
 const result=sync.merge({decks:[{id:"d",name:"old",updatedAt:20}]},{decks:[{id:"d",name:"new",updatedAt:40}],_deleted:{decks:[{id:"d",deletedAt:30}]}});
 assert.equal(result.decks[0].name,"new");
 assert.equal(result._deleted.decks.length,0);
}
{
 const result=sync.stamp({notes:[{id:"n",title:"edited",updatedAt:10}]},{notes:[{id:"n",title:"old",updatedAt:10}]},50);
 assert.equal(result.notes[0].updatedAt,50);
}
{
 const result=sync.stamp({notes:[]},{notes:[{id:"n",updatedAt:10}]},50);
 assert.equal(result._deleted.notes[0].id,"n");
 assert.equal(result._deleted.notes[0].deletedAt,50);
}
console.log("Workspace sync tests passed");
