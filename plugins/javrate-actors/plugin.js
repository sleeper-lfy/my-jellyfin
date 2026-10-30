var SITE = 'https://www.javrate.com';
var DETAIL = /\/actor\/detail\/([^\/?#]+)\.html/;

function trim(value) {
    return String(value == null ? '' : value).replace(/^\s+|\s+$/g, '');
}

function decodeText(value) {
    if (value === null || typeof value === 'undefined') return '';
    var text = String(value);
    text = text.replace(/<[^>]*>/g, ' ');
    text = text.replace(/&nbsp;/gi, ' ').replace(/&lt;/gi, '<').replace(/&gt;/gi, '>')
        .replace(/&quot;/gi, '"').replace(/&#0*39;|&apos;/gi, "'").replace(/&amp;/gi, '&');
    text = text.replace(/&#x0*([0-9a-f]+);/gi, function (match, code) {
        return String.fromCharCode(parseInt(code, 16));
    });
    text = text.replace(/&#0*([0-9]+);/g, function (match, code) {
        return String.fromCharCode(parseInt(code, 10));
    });
    return text.replace(/\s+/g, ' ').trim();
}

function hostOf(url) {
    var match = /^https?:\/\/([^\/?#]+)/i.exec(String(url || ''));
    return match ? match[1].split(':')[0].toLowerCase() : '';
}

function urlFor(base, path) {
    var value = trim(base) || 'https://r.jina.ai';
    value = value.replace(/\/+$/, '');
    if (/(^|\.)r\.jina\.ai$/i.test(hostOf(value))) return value + '/' + SITE + path;
    return value + path;
}

function actorId(url) {
    var match = String(url || '').match(DETAIL);
    return match ? match[1] : '';
}

function upgradePhoto(url) {
    var value = decodeText(url);
    if (!value) return '';
    return value.replace(/_s\.webp(\?.*)?$/i, '_l.webp$1');
}

function buildRequest(input) {
    if (input.operation !== 'actors') throw new Error('此插件只提供演员头像搜索');
    var query = trim(input.query || '');
    if (!query) throw new Error('请输入演员姓名');
    var base = (input.config && input.config.base_url) || 'https://r.jina.ai';
    return {url: urlFor(base, '/actor/list/' + encodeURIComponent(query.toLowerCase()))};
}

function parseResponse(input) {
    if (input.operation !== 'actors') throw new Error('此插件只提供演员头像搜索');
    var body = String(input.body || '');
    var start = body.indexOf('共找到AV女優');
    if (start < 0) {
        if (/Just a moment|Cloudflare|403 Forbidden|Access denied|Failed to fetch|Warning:\s*Target/i.test(body)) {
            throw new Error('JavRate 经 r.jina.ai 读取失败：站点验证或 Reader 限流；请稍后重试，并确认应用内代理可用');
        }
        return [];
    }
    var end = body.length;
    var markers = ['查找:', '## [全部女優]', '全部女優](', '## 本月出道女優'];
    for (var index = 0; index < markers.length; index++) {
        var position = body.indexOf(markers[index], start);
        if (position >= 0 && position < end) end = position;
    }
    var section = body.slice(start, end);
    var pattern = /\[!\[[^\]]*\]\((https?:\/\/[^)]+)\)([\s\S]*?)\]\((https?:\/\/[^)]+\/actor\/detail\/[^)]+\.html)(?:\s+"([^"]*)")?\)/g;
    var records = [], seen = {}, match;
    while ((match = pattern.exec(section)) !== null && records.length < 20) {
        var id = actorId(match[3]);
        if (!id || seen[id]) continue;
        seen[id] = true;
        var heading = String(match[2]).match(/###\s*([^\n]+)/);
        var name = decodeText(match[4] || '');
        if (!name && heading) {
            name = decodeText(heading[1].replace(/\s+(?:\d+\s*部AV|\d+\s*歲|\|).*$/i, ''));
        }
        if (!name || name.length > 200) continue;
        var photo = upgradePhoto(match[1]);
        if (/_thumbnail\.webp|_cover\.webp/i.test(photo)) continue;
        var url = decodeText(match[3]);
        records.push({
            id: 'javrate:' + id,
            name: name,
            gender: 'female',
            aliases: [],
            url: url,
            photo: photo || null,
            photo_page: url
        });
    }
    return records;
}
