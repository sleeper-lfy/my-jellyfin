function buildRequest(input) {
    if (input.operation !== 'actors') throw new Error('此插件只提供演员头像搜索');
    var base=(input.config.base_url || 'https://www.wikidata.org').replace(/\/$/, '');
    var query=(input.query || '').trim();
    if (!query) throw new Error('请输入演员姓名');
    return {url:base+'/w/api.php?action=wbsearchentities&format=json&language=ja&uselang=ja&limit=6&search='+encodeURIComponent(query)};
}

function parseResponse(input) {
    var data=JSON.parse(input.body);
    if (data.error) throw new Error(data.error.info || 'Wikimedia API 返回错误');
    var base=(input.config.base_url || 'https://www.wikidata.org').replace(/\/$/, '');
    if (data.search) {
        return {records:[],followups:data.search.slice(0,6).filter(function(row){return /^Q[0-9]+$/.test(row.id);}).map(function(row){
            return {url:base+'/w/api.php?action=wbgetentities&format=json&props=labels%7Caliases%7Cdescriptions%7Cclaims&languages=ja%7Czh%7Cen&ids='+row.id};
        })};
    }
    if (data.entities) {
        var followups=[];
        Object.keys(data.entities).forEach(function(id){
            var entity=data.entities[id];
            var claims=entity.claims || {};
            function values(key) {return (claims[key] || []).map(function(claim){return ((claim.mainsnak || {}).datavalue || {}).value;}).filter(function(value){return value != null;});}
            // Do not infer a person's gender from their name or a search result.
            if (!values('P31').some(function(value){return value.id==='Q5';}) ||
                !values('P21').some(function(value){return value.id==='Q6581072';})) return;
            var images=values('P18');
            if (!images.length || typeof images[0] !== 'string') return;
            var labels=entity.labels || {};
            var label=labels.ja || labels.zh || labels.en;
            if (!label || !label.value) return;
            var aliases=[];
            Object.keys(labels).forEach(function(language){aliases.push(labels[language].value);});
            Object.keys(entity.aliases || {}).forEach(function(language){entity.aliases[language].forEach(function(alias){aliases.push(alias.value);});});
            aliases=aliases.filter(function(name,index){return typeof name==='string' && name!==label.value && aliases.indexOf(name)===index;}).slice(0,100);
            var person={id:'wikidata:'+id,name:label.value,gender:'female',aliases:aliases,
                url:'https://www.wikidata.org/wiki/'+id,
                description:((entity.descriptions || {}).ja || (entity.descriptions || {}).en || {}).value || ''};
            followups.push({url:'https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url%7Cextmetadata&titles='+encodeURIComponent('File:'+images[0]),context:person});
        });
        return {records:[],followups:followups};
    }
    if (data.query && data.query.pages && input.context) {
        var records=[];
        Object.keys(data.query.pages).forEach(function(key){
            var info=(data.query.pages[key].imageinfo || [])[0];
            if (!info || !/^https:\/\/upload\.wikimedia\.org\//.test(info.url || '')) return;
            var metadata=info.extmetadata || {};
            var person=input.context;
            person.photo=info.url;
            person.photo_page=info.descriptionurl || '';
            person.photo_license=(metadata.LicenseShortName || {}).value || '';
            person.photo_attribution=(metadata.Artist || {}).value || '';
            records.push(person);
        });
        return records;
    }
    return [];
}
