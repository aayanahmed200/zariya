"use strict";
const assert = require("node:assert/strict");
const sync = require("../webapp/static/workspace-sync.js");

{
  const remote={sessions:[{id:"chat-1",title:"Server",createdAt:10,updatedAt:100}]};
  const cached={sessions:[{id:"chat-1",title:"Offline edit",createdAt:10,updatedAt:200}]};
  assert.equal(sync.merge(remote,cached).sessions[0].title,"Offline edit");
}
{
  const remote={notes:[{id:"note-1",body:"New server copy",createdAt:10,updatedAt:300}]};
  const cached={notes:[{id:"note-1",body:"Old local copy",createdAt:10,updatedAt:200}]};
  assert.equal(sync.merge(remote,cached).notes[0].body,"New server copy");
}
{
  const remote={sessions:[{id:"chat-1",title:"Stale copy",createdAt:10,updatedAt:200}]};
  const cached={sessions:[],_deleted:{sessions:[{id:"chat-1",deletedAt:300}]}};
  const merged=sync.merge(remote,cached);
  assert.deepEqual(merged.sessions,[]);
  assert.deepEqual(merged._deleted.sessions,[{id:"chat-1",deletedAt:300}]);
}
{
  const remote={decks:[{id:"deck-1",name:"Stale deck",createdAt:10,updatedAt:200}]};
  const cached={decks:[{id:"deck-1",name:"Recreated deck",createdAt:10,updatedAt:400}],_deleted:{decks:[{id:"deck-1",deletedAt:300}]}};
  const merged=sync.merge(remote,cached);
  assert.equal(merged.decks[0].name,"Recreated deck");
  assert.deepEqual(merged._deleted.decks,[]);
}
{
  const previous={notes:[{id:"note-1",title:"Old title",body:"Old body",createdAt:50,updatedAt:100}]};
  const current={notes:[{id:"note-1",title:"New title",body:"Old body",createdAt:50,updatedAt:100}]};
  assert.equal(sync.stamp(current,previous,200).notes[0].updatedAt,200);
}
{
  const previous={decks:[{id:"deck-1",name:"Removed",createdAt:50,updatedAt:100}]};
  const stamped=sync.stamp({decks:[]},previous,200);
  assert.deepEqual(stamped.decks,[]);
  assert.deepEqual(stamped._deleted.decks,[{id:"deck-1",deletedAt:200}]);
}
{
  const normalized=sync.normalize({sessions:[null,{id:"one"}],_deleted:{sessions:[{id:"one",deletedAt:12},{id:"one",deletedAt:20}]}});
  assert.deepEqual(normalized.sessions,[{id:"one"}]);
  assert.deepEqual(normalized._deleted.sessions,[{id:"one",deletedAt:20}]);
  assert.deepEqual(sync.empty()._deleted,{sessions:[],notes:[],decks:[]});
}
console.log("Workspace sync tests passed");
