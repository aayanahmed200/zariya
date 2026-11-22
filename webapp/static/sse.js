(function attachSSE(root){
  "use strict";

  function parseEventBlock(block){
    const dataLines=String(block).split("\n")
      .filter(line=>line.startsWith("data:"))
      .map(line=>line.slice(5).replace(/^ /,""));
    if(!dataLines.length) return null;
    const data=dataLines.join("\n");
    try{
      return JSON.parse(data);
    }catch(error){
      return null;
    }
  }

  // Accept arbitrary network chunks, CRLF/LF event boundaries, and a final
  // unterminated event. Returns the unconsumed tail for the next chunk.
  function consume(buffer,onEvent,flush=false){
    let pending=String(buffer||"").replace(/\r\n/g,"\n").replace(/\r/g,"\n");
    let boundary;
    while((boundary=pending.indexOf("\n\n"))!==-1){
      const block=pending.slice(0,boundary);
      pending=pending.slice(boundary+2);
      const event=parseEventBlock(block);
      if(event!==null && typeof onEvent==="function") onEvent(event);
    }
    if(flush && pending.trim()){
      const event=parseEventBlock(pending);
      if(event!==null && typeof onEvent==="function") onEvent(event);
      pending="";
    }
    return pending;
  }

  const api={consume,parseEventBlock};
  root.ZariyaSSE=api;
  if(typeof module!=="undefined" && module.exports) module.exports=api;
})(typeof window!=="undefined" ? window : globalThis);
