function buildRequest(input) {
    var base = input.config.base_url.replace(/\/$/, '');
    if (input.operation === 'search') return {url: base + '/search/shows?q=' + encodeURIComponent(input.query || '')};
    if (input.operation === 'detail') {
        var match = /\/shows\/(\d+)/.exec(input.url || '');
        if (!match) throw new Error('需要 TVmaze /shows/数字 的详情网址');
        return {url: base + '/shows/' + match[1] + '?embed[]=cast&embed[]=images'};
    }
    // Default: newest assigned show IDs from the public update index, not a fabricated added date.
    var page = input.category || input.config.category || '';
    if (!page || page === 'latest') return {url: base + '/updates/shows'};
    if (!/^\d+$/.test(page)) throw new Error('分类填写 latest 或非负索引页码');
    return {url: base + '/shows?page=' + page};
}
function parseResponse(input) {
    var data = JSON.parse(input.body);
    var base=input.config.base_url.replace(/\/$/, '');
    if (/\/updates\/shows$/.test(input.url)) {
        var newest=Object.keys(data).sort(function(a,b){return Number(b)-Number(a);}).slice(0,12);
        return {followups:newest.map(function(id){return {url:base+'/shows/'+id+'?embed[]=cast&embed[]=images'};}), records:[]};
    }
    if (input.operation==='search' && Array.isArray(data) && data.length && data[0].show) {
        return {followups:data.slice(0,10).map(function(row){return {url:base+'/shows/'+row.show.id+'?embed[]=cast&embed[]=images'};}),records:[]};
    }
    var rows = Array.isArray(data) ? data : [data];
    return rows.map(function (row) {
        var s = row.show || row;
        return {id: String(s.id), title: s.name, kind: 'series', year: s.premiered ? parseInt(s.premiered.slice(0,4)) : null,
            released: s.premiered, site_added: null, url: s.url, rating: s.rating ? s.rating.average : null,
            overview: (s.summary || '').replace(/<[^>]*>/g,''), tags: s.genres || [], aliases: [],
            external_ids: {tvmaze: String(s.id), imdb: s.externals ? s.externals.imdb : null},
            poster: s.image ? (s.image.original || s.image.medium) : null,
            stills: ((s._embedded || {}).images || []).filter(function(image){return image.type==='background';}).slice(0,40).map(function(image){return image.resolutions.original.url;}),
            actors: ((s._embedded || {}).cast || []).map(function (entry) {
                var p=entry.person;
                return {id:'tvmaze:'+p.id, name:p.name, gender:p.gender==='Female'?'female':p.gender==='Male'?'male':'unknown',
                    aliases:[], photo:p.image ? (p.image.original || p.image.medium) : null, birthday:p.birthday};
            })};
    });
}
