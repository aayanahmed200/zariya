"use strict";
const assert = require("node:assert/strict");
const { consume, parseEventBlock } = require("../webapp/static/sse.js");

function parseChunks(chunks, flush = true){
  const events=[];
  let pending="";
  for(const chunk of chunks) pending=consume(pending+chunk,event=>events.push(event));
  if(flush) pending=consume(pending,event=>events.push(event),true);
  return {events,pending};
}

{
  const result=parseChunks([
    'data: {"delta":"hel',
    'lo"}\n\n',
    'data: {"delta":" world"}\n\n',
    'data: {"done":true,"provider":"ai_gateway"}\n\n'
  ]);
  assert.deepEqual(result.events,[
    {delta:"hello"},
    {delta:" world"},
    {done:true,provider:"ai_gateway"}
  ]);
  assert.equal(result.pending,"");
}

{
  const result=parseChunks([
    'data: {"delta":"one"}\r\n\r\n',
    'data: {"delta":"two"}\r\n\r\n'
  ]);
  assert.deepEqual(result.events,[{delta:"one"},{delta:"two"}]);
}

{
  const events=[];
  const pending=consume('data: {"delta":"partial"}',event=>events.push(event));
  assert.equal(events.length,0);
  assert.deepEqual(parseEventBlock('data: {"done":true}'),{done:true});
  consume(pending,event=>events.push(event),true);
  assert.deepEqual(events,[{delta:"partial"}]);
}

{
  const result=parseChunks([
    ': keep-alive\n\n',
    'event: message\ndata: {"delta":"a"}\ndata: {"delta":"b"}\n\n',
    'data: not-json\n\n'
  ]);
  assert.deepEqual(result.events,[]);
}

console.log("SSE parser tests passed");
