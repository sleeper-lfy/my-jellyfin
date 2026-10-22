function buildRequest(input) {
    var base=input.config.base_url.replace(/\/$/, '');
    if(input.operation==='detail') {
        var m=/\/(?:details|metadata)\/([a-zA-Z0-9_.-]+)/.exec(input.url || '');
        if(!m) throw new Error('请输入 archive.org/details/编号 的详情网址');
        return {url:base+'/metadata/'+m[1]};
    }
    var category=input.category || input.config.category || 'feature_films';
    if(!/^[a-zA-Z0-9_-]+$/.test(category)) throw new Error('分类须为 collection 标识符');
    var q='mediatype:movies AND collection:'+category;
    if(input.operation==='search') q+=' AND title:('+String(input.query || '').replace(/[+\-!(){}\[\]^"~*?:\\/]/g,' ') + ')';
    var fields=['identifier','title','year','date','addeddate','description','subject','creator'];
    return {url:base+'/advancedsearch.php?q='+encodeURIComponent(q)+'&output=json&rows=50&sort[]=addeddate+desc&'+fields.map(function(f){return 'fl[]='+f;}).join('&')};
}
function parseResponse(input) {
    var data=JSON.parse(input.body);
    var rows=data.response ? data.response.docs : [data.metadata];
    return rows.filter(function(m){return !!m;}).map(function(m){
        function scalar(x){return Array.isArray(x)?x[0]:x;}
        var date=String(scalar(m.year) || scalar(m.date) || '');
        return {id:m.identifier,title:String(scalar(m.title)),kind:'movie',year:/^\d{4}/.test(date)?parseInt(date.slice(0,4)):null,
            released:scalar(m.date)||null,site_added:scalar(m.addeddate)||null,url:'https://archive.org/details/'+m.identifier,
            overview:String(scalar(m.description)||'').replace(/<[^>]*>/g,''),
            tags:Array.isArray(m.subject)?m.subject:String(m.subject||'').split(';').filter(function(x){return !!x;}),
            actors:[], directors:[], poster:'https://archive.org/services/img/'+m.identifier, rating:null,
            external_ids:{archive:m.identifier}};
    });
}
