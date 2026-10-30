function decodeText(value) {
    if (value === null || typeof value === 'undefined') return '';
    var text = String(value);
    text = text.replace(/<[^>]*>/g, ' ');
    text = text.replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
        .replace(/&lt;/g, '<').replace(/&gt;/g, '>');
    text = text.replace(/&#x([0-9a-fA-F]+);/g, function (match, code) {
        return String.fromCharCode(parseInt(code, 16));
    });
    text = text.replace(/&#([0-9]+);/g, function (match, code) {
        return String.fromCharCode(parseInt(code, 10));
    });
    return text.replace(/\s+/g, ' ').trim();
}

function attribute(tag, name) {
    var pattern = new RegExp('\\b' + name + '\\s*=\\s*("([^"]*)"|\'([^\']*)\')', 'i');
    var match = String(tag).match(pattern);
    if (!match) return '';
    return decodeText(match[2] !== undefined ? match[2] : match[3]);
}

function originOf(value) {
    var match = String(value || '').match(/^(https?:\/\/[^\/]+)/i);
    return match ? match[1] : 'https://www.javbus.com';
}

function absolute(origin, value) {
    var address = String(value || '').trim();
    if (!address) return '';
    if (/^https?:\/\//i.test(address)) return address;
    if (address.indexOf('//') === 0) return 'https:' + address;
    if (address.charAt(0) === '/') return origin + address;
    return origin + '/' + address;
}

function validImage(address) {
    if (!address) return false;
    if (!/\.(jpe?g|png|webp)(?:[?#].*)?$/i.test(address)) return false;
    return !/nowprinting|noimage|default|blank|spacer/i.test(address);
}

function imageIn(block, preferredName) {
    var tags = String(block || '').match(/<img\b[^>]*>/gi) || [];
    var fallback = null, actress = null, named = null;
    var wanted = preferredName ? decodeText(preferredName) : '';
    for (var index = 0; index < tags.length; index++) {
        var tag = tags[index];
        var address = attribute(tag, 'src') || attribute(tag, 'data-src') || attribute(tag, 'data-original');
        if (!validImage(address)) continue;
        var label = attribute(tag, 'alt') || attribute(tag, 'title');
        var entry = {url: address, label: label};
        if (!fallback) fallback = entry;
        if (!actress && (/\/pics\/actress\//i.test(address) || /\/actress\//i.test(address))) actress = entry;
        if (!named && wanted && label && decodeText(label).indexOf(wanted) >= 0) named = entry;
    }
    return named || actress || fallback;
}

function starId(address) {
    var match = String(address || '').match(/\/star\/([A-Za-z0-9_-]+)/);
    return match ? match[1] : '';
}

function shortName(block, image) {
    if (image && image.label) {
        var label = decodeText(image.label);
        if (label) return label;
    }
    var spans = String(block || '').match(/<span\b[^>]*>[\s\S]*?<\/span>/gi) || [];
    for (var index = 0; index < spans.length; index++) {
        var value = decodeText(spans[index]);
        if (value && value.length <= 80 && !/^\d+$/.test(value)) return value;
    }
    var text = decodeText(String(block || '').replace(/<img\b[^>]*>/gi, ' '));
    text = text.replace(/^(女优|女優|演员|演員)\s*[：:]\s*/, '');
    text = text.replace(/\s+[\d,]+(?:\s*部.*)?$/, '');
    return text && text.length <= 200 ? text : '';
}

function recordFrom(entry) {
    return {
        id: 'javbus:' + entry.id,
        name: entry.name,
        gender: 'female',
        aliases: [],
        url: entry.url,
        photo: entry.photo,
        photo_page: entry.url
    };
}

function canonicalStar(body) {
    var links = String(body || '').match(/<link\b[^>]*>/gi) || [];
    for (var index = 0; index < links.length; index++) {
        var rel = attribute(links[index], 'rel').toLowerCase();
        if (rel.split(/\s+/).indexOf('canonical') < 0) continue;
        var href = attribute(links[index], 'href');
        var id = starId(href);
        if (id) return {id: id, url: href};
    }
    var fallback = String(body || '').match(/\/star\/([A-Za-z0-9_-]+)/);
    return fallback ? {id: fallback[1], url: '/star/' + fallback[1]} : null;
}

function pageTitle(body) {
    var match = String(body || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    if (!match) return '';
    return decodeText(match[1]).split(/\s+[-|–—]\s+/)[0].trim();
}

function parseSingleStar(input) {
    var origin = originOf(input.config && input.config.base_url);
    var body = String(input.body || '');
    var star = canonicalStar(body);
    var contextQuery = decodeText((input.context || {}).query || '');
    var image = imageIn(body, contextQuery);
    if (!star || !image || !image.url) return {records: [], followups: []};
    var label = decodeText(image.label || '');
    var matchesName = contextQuery && label && label.indexOf(contextQuery) >= 0;
    if (!(/\/pics\/actress\//i.test(image.url) || /\/actress\//i.test(image.url) || matchesName)) {
        return {records: [], followups: []};
    }
    var name = label || contextQuery || pageTitle(body);
    if (!name || name.length > 200) return {records: [], followups: []};
    return {records: [recordFrom({id: star.id, name: name, url: absolute(origin, star.url), photo: absolute(origin, image.url)})], followups: []};
}

function parseSearch(input) {
    var origin = originOf(input.config && input.config.base_url);
    var body = String(input.body || '');
    var pattern = /<a\b[^>]*href\s*=\s*["'][^"']*\/star\/[^"']*["'][^>]*>[\s\S]*?<\/a>/gi;
    var found = {}, order = [], match;
    while ((match = pattern.exec(body)) !== null) {
        var block = match[0];
        var opening = block.match(/<a\b[^>]*>/i);
        var href = opening ? attribute(opening[0], 'href') : '';
        var id = starId(href);
        if (!id) continue;
        if (!found[id]) {
            found[id] = {id: id, url: absolute(origin, href), name: '', photo: ''};
            order.push(id);
        }
        var image = imageIn(block, found[id].name);
        if (image && image.url && !found[id].photo) found[id].photo = absolute(origin, image.url);
        if (!found[id].name) found[id].name = shortName(block, image);
    }
    var records = [], followups = [];
    for (var index = 0; index < order.length; index++) {
        var entry = found[order[index]];
        if (!entry.name || !entry.url) continue;
        if (entry.photo) records.push(recordFrom(entry));
        else followups.push({url: entry.url, context: {id: entry.id, name: entry.name, url: entry.url}});
        if (records.length + followups.length >= 12) break;
    }
    if (!order.length) return parseSingleStar(input);
    return {records: records, followups: followups};
}

function parseStar(input) {
    var context = input.context || {};
    var id = String(context.id || starId(context.url) || '');
    var name = decodeText(context.name || '');
    if (!id || !name) return [];
    var image = imageIn(String(input.body || ''), name);
    if (!image || !image.url) return [];
    var origin = originOf(input.config && input.config.base_url);
    return [recordFrom({
        id: id,
        name: name,
        url: absolute(origin, context.url || ('/star/' + id)),
        photo: absolute(origin, image.url)
    })];
}

function readerUrl(url) {
    return 'https://r.jina.ai/' + url;
}

function parseMarkdownLinks(body) {
    var links = [], pattern = /\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g, match;
    while ((match = pattern.exec(String(body || ''))) !== null) {
        var id = starId(match[2]);
        var name = decodeText(match[1]);
        if (!id || !name) continue;
        links.push({id: id, url: match[2], name: name});
    }
    return links;
}

function parseMarkdownImages(body) {
    var images = [], pattern = /!\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/g, match;
    while ((match = pattern.exec(String(body || ''))) !== null) {
        if (!validImage(match[2])) continue;
        if (!(/\/pics\/actress\//i.test(match[2]) || /\/actress\//i.test(match[2]))) continue;
        images.push({url: match[2], label: decodeText(match[1])});
    }
    return images;
}

function parseReaderSearch(input) {
    var body = String(input.body || '');
    var links = parseMarkdownLinks(body);
    var images = parseMarkdownImages(body);
    var records = [], followups = [];
    var paired = links.length > 0 && images.length === links.length;
    for (var index = 0; index < links.length && records.length + followups.length < 12; index++) {
        var link = links[index];
        if (paired) records.push(recordFrom({id: link.id, name: link.name, url: link.url, photo: images[index].url}));
        else followups.push({url: readerUrl(link.url), context: {id: link.id, name: link.name, url: link.url, reader: true, query: (input.context || {}).query || ''}});
    }
    return {records: records, followups: followups};
}

function parseReaderStar(input) {
    var context = input.context || {};
    var images = parseMarkdownImages(input.body);
    var name = decodeText(context.name || '') || (images.length ? images[0].label : '');
    if (!context.id || !name || !images.length) return [];
    var url = absolute(originOf(input.config && input.config.base_url), context.url || ('/star/' + context.id));
    return [recordFrom({id: context.id, name: name, url: url, photo: images[0].url})];
}

function buildRequest(input) {
    if (input.operation !== 'actors') throw new Error('此插件只提供演员头像搜索');
    var query = String(input.query || '').trim();
    if (!query) throw new Error('请输入演员姓名');
    var origin = originOf(input.config && input.config.base_url);
    return {url: origin + '/searchstar/' + encodeURIComponent(query), context: {query: query}};
}

function parseResponse(input) {
    if (input.operation !== 'actors') throw new Error('此插件只提供演员头像搜索');
    if (String(input.body || '').indexOf('driver-verify') >= 0) {
        var context = input.context || {};
        if (context.reader) throw new Error('站点要求浏览器验证（driver-verify），经 r.jina.ai 读取后仍被拦截；请稍后重试或更换网络出口');
        if (!input.url) throw new Error('站点返回浏览器验证页（driver-verify），自动抓取被拦截');
        return {records: [], followups: [{url: readerUrl(input.url), context: {query: context.query || '', reader: true}}]};
    }
    if (input.context && input.context.reader) {
        if (input.context.id) return parseReaderStar(input);
        return parseReaderSearch(input);
    }
    if (input.context && input.context.id) return parseStar(input);
    return parseSearch(input);
}
