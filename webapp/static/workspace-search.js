(function(root){
  'use strict';

  function normalize(value){
    return String(value == null ? '' : value).normalize('NFKC').toLocaleLowerCase();
  }

  function matchesAny(fields, query){
    const needle=normalize(query).trim();
    if(!needle) return true;
    const values=Array.isArray(fields) ? fields : [fields];
    return values.some(value=>normalize(value).includes(needle));
  }

  root.ZariyaWorkspaceSearch=Object.freeze({normalize,matchesAny});
})(window);
