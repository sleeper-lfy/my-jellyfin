var API = 'https://api.themoviedb.org/3';

function buildRequest(input) {
    if (input.operation === 'detail') {
        var match = /^https?:\/\/(?:www\.)?themoviedb\.org\/(movie|tv)\/([1-9]\d*)(?:-[^/?#]*)?(?:[/?#].*)?$/i.exec(input.url || '');
        if (!match) throw new Error('请粘贴 TMDB 的电影或剧集详情页链接');
        var type = match[1].toLowerCase();
        if ((input.kind === 'movie' && type !== 'movie') || (input.kind === 'series' && type !== 'tv')) {
            throw new Error('TMDB 链接与当前作品类型不匹配');
        }
        return {url: API + '/' + type + '/' + match[2] + '?language=zh-CN&append_to_response=credits,external_ids,alternative_titles'};
    }
    var query = (input.query || '').trim();
    if (!query) throw new Error('请输入影片或剧集名称');
    var path = input.kind === 'movie' ? 'movie' : input.kind === 'series' ? 'tv' : 'multi';
    return {url: API + '/search/' + path + '?language=zh-CN&include_adult=false&query=' + encodeURIComponent(query)};
}

function artwork(path, size) {
    return typeof path === 'string' && /^\/[a-zA-Z0-9_-]+\.(?:jpg|jpeg|png|webp)$/i.test(path)
        ? 'https://image.tmdb.org/t/p/' + size + path : null;
}

function strings(values) {
    return values.filter(function (value, index) {
        return typeof value === 'string' && value.trim() && values.indexOf(value) === index;
    });
}

function record(item, type) {
    var movie = type === 'movie';
    var title = movie ? item.title : item.name;
    var original = movie ? item.original_title : item.original_name;
    title = title || original;
    if (typeof title !== 'string' || !title.trim() || !Number.isSafeInteger(item.id) || item.id <= 0 || item.adult === true) return null;
    var date = movie ? item.release_date : item.first_air_date;
    var year = /^\d{4}-\d{2}-\d{2}$/.test(date || '') ? Number(date.slice(0, 4)) : null;
    if (year !== null && (year < 1800 || year > 2200)) year = null;
    var ids = {tmdb: String(item.id)};
    var external = item.external_ids || {};
    var imdb = external.imdb_id || item.imdb_id;
    if (/^tt\d+$/.test(imdb || '')) ids.imdb = imdb;
    if (!movie && Number.isSafeInteger(external.tvdb_id) && external.tvdb_id > 0) ids.tvdb = String(external.tvdb_id);
    var credits = item.credits || {};
    var alternatives = item.alternative_titles || {};
    var aliases = strings([original].concat((alternatives.titles || alternatives.results || []).map(function (entry) { return entry.title; })));
    return {
        id: type + ':' + item.id,
        title: title,
        kind: movie ? 'movie' : 'series',
        year: year,
        released: year === null ? null : date,
        url: 'https://www.themoviedb.org/' + type + '/' + item.id,
        rating: item.vote_count > 0 && typeof item.vote_average === 'number' && item.vote_average >= 0 && item.vote_average <= 10 ? item.vote_average : null,
        overview: typeof item.overview === 'string' ? item.overview : '',
        tags: strings((item.genres || []).map(function (genre) { return genre.name; })),
        aliases: aliases.filter(function (alias) { return alias !== title; }).slice(0, 100),
        directors: strings((credits.crew || []).filter(function (person) { return person.job === 'Director'; }).map(function (person) { return person.name; })),
        actors: (credits.cast || []).filter(function (person) { return person.id && person.name; }).slice(0, 40).map(function (person) {
            return {
                id: 'tmdb:' + person.id,
                name: person.name,
                aliases: strings([person.original_name]).filter(function (name) { return name !== person.name; }),
                gender: person.gender === 1 ? 'female' : person.gender === 2 ? 'male' : 'unknown',
                photo: artwork(person.profile_path, 'w185')
            };
        }),
        external_ids: ids,
        poster: artwork(item.poster_path, 'w500'),
        cover: artwork(item.backdrop_path, 'w1280')
    };
}

function parseResponse(input) {
    var data = JSON.parse(input.body);
    if (input.operation === 'detail') {
        var detail = /^https:\/\/api\.themoviedb\.org\/3\/(movie|tv)\/(\d+)\?/.exec(input.url);
        var item = detail && String(data.id) === detail[2] ? record(data, detail[1]) : null;
        if (!item) throw new Error('TMDB 未返回链接对应的作品资料');
        return [item];
    }
    if (!Array.isArray(data.results)) throw new Error('TMDB 搜索响应缺少结果列表');
    var scope = /\/search\/(movie|tv|multi)\?/.exec(input.url)[1];
    return data.results.map(function (item) {
        var type = scope === 'multi' ? item.media_type : scope;
        return type === 'movie' || type === 'tv' ? record(item, type) : null;
    }).filter(Boolean);
}
