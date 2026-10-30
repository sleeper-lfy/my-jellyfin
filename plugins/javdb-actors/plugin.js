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

function attribute(tag, name) {
    var pattern = new RegExp('\\b' + name + '\\s*=\\s*("([^"]*)"|\'([^\']*)\')', 'i');
    var match = String(tag).match(pattern);
    if (!match) return '';
    return decodeText(match[2] !== undefined ? match[2] : match[3]);
}

function originOf(value) {
    var match = String(value || '').match(/^(https?:\/\/[^\/]+)/i);
    return match ? match[1] : 'https://javdb.com';
}

function absolute(origin, value) {
    var address = String(value || '').trim();
    if (!address) return '';
    if (/^https?:\/\//i.test(address)) return address;
    if (address.indexOf('//') === 0) return 'https:' + address;
    if (address.charAt(0) === '/') return origin + address;
    return origin + '/' + address;
}

function actorId(address) {
    var match = String(address || '').match(/\/actors\/([A-Za-z0-9_-]+)/);
    return match ? match[1] : '';
}

function uniqueAliases(title, name) {
    var seen = {}, result = [], parts = String(title || '').split(/[,，]/);
    for (var index = 0; index < parts.length; index++) {
        var alias = decodeText(parts[index]);
        if (!alias || alias === name || seen[alias]) continue;
        seen[alias] = true;
        result.push(alias);
        if (result.length >= 100) break;
    }
    return result;
}

function parseActors(input) {
    var origin = originOf(input.config && input.config.base_url);
    var body = String(input.body || '');
    var pattern = /<a\b[^>]*href\s*=\s*["'][^"']*\/actors\/[^"']*["'][^>]*>[\s\S]*?<\/a>/gi;
    var records = [], seen = {}, match;
    while ((match = pattern.exec(body)) !== null && records.length < 20) {
        var block = match[0];
        var opening = block.match(/<a\b[^>]*>/i);
        var href = opening ? attribute(opening[0], 'href') : '';
        var id = actorId(href);
        if (!id || seen[id]) continue;
        seen[id] = true;
        var strong = block.match(/<strong\b[^>]*>([\s\S]*?)<\/strong>/i);
        var title = opening ? attribute(opening[0], 'title') : '';
        var name = strong ? decodeText(strong[1]) : '';
        if (!name) name = decodeText(String(title).split(/[,，]/)[0] || '');
        if (!name || name.length > 200) continue;
        var image = block.match(/<img\b[^>]*>/i);
        var photo = '';
        if (image) {
            photo = attribute(image[0], 'src') || attribute(image[0], 'data-src') || attribute(image[0], 'data-original');
            if (/actor_unknow|noimage|default|blank/i.test(photo)) photo = '';
        }
        var url = absolute(origin, href);
        records.push({
            id: 'javdb:' + id,
            name: name,
            gender: 'unknown',
            aliases: uniqueAliases(title, name),
            url: url,
            photo: photo ? absolute(origin, photo) : null,
            photo_page: url
        });
    }
    return records;
}

function buildRequest(input) {
    if (input.operation !== 'actors') throw new Error('此插件只提供演员头像搜索');
    var query = String(input.query || '').trim();
    if (!query) throw new Error('请输入演员姓名');
    var origin = originOf(input.config && input.config.base_url);
    return {url: origin + '/search?f=actor&q=' + encodeURIComponent(query)};
}

function parseResponse(input) {
    if (input.operation !== 'actors') throw new Error('此插件只提供演员头像搜索');
    var body = String(input.body || '');
    var records = parseActors(input);
    if (!records.length && /<title[^>]*>\s*Just a moment|__cf_chl|challenge-running|Verifying you are human/i.test(body)) {
        throw new Error('JavDB 返回 Cloudflare 验证页；请在应用设置中配置可用代理后重试');
    }
    return records;
}
