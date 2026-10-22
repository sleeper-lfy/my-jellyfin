function buildRequest(input) {
    var base = input.config.base_url.replace(/\/$/, '');
    if (input.operation === 'detail') return {url: input.url};
    var path = input.category || input.config.category || '/catalog.json';
    return {url: base + '/' + path.replace(/^\//, '')};
}
function parseResponse(input) {
    var data = JSON.parse(input.body);
    var items = Array.isArray(data) ? data : (data.items || [data]);
    return items.map(function (item) {
        if (!item.id || !item.title || !item.url) throw new Error('缺少 id/title/url');
        return {
            id: String(item.id), title: item.title, kind: item.kind || 'movie', year: item.year || null,
            aliases: item.aliases || [], tags: item.tags || [], actors: item.actors || [],
            directors: item.directors || [], overview: item.overview || '', poster: item.poster || null,
            rating: item.rating === undefined ? null : item.rating,
            released: item.released || null, site_added: item.site_added || null, url: item.url,
            stills: item.stills || [], download_method: item.download_method || null, download_url: item.download_url || []
        };
    });
}
