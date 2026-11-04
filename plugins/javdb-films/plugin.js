/* Metadata-only parser. No video, torrent or magnet links are returned. */
var SITE = 'javdb';
function text(value) {
    return String(value || '').replace(/<[^>]*>/g,' ').replace(/&nbsp;/gi,' ')
        .replace(/&quot;/gi,'"').replace(/&apos;|&#0*39;/gi,"'")
        .replace(/&lt;/gi,'<').replace(/&gt;/gi,'>').replace(/&amp;/gi,'&')
        .replace(/&#x([0-9a-f]+);/gi,function(_,n){return String.fromCharCode(parseInt(n,16));})
        .replace(/&#([0-9]+);/g,function(_,n){return String.fromCharCode(parseInt(n,10));})
        .replace(/\s+/g,' ').trim();
}
function attr(tag,key) {
    var found=String(tag).match(new RegExp('\\b'+key+'\\s*=\\s*(?:"([^"]*)"|\'([^\']*)\')','i'));
    return found ? text(found[1]===undefined ? found[2] : found[1]) : '';
}
function origin(input) {
    var base=String(input.config && input.config.base_url || (SITE==='javbus'?'https://www.javbus.com':'https://javdb.com'));
    var found=base.match(/^(https?:\/\/[^/]+)/i);
    if(!found)throw new Error('来源地址无效');
    return found[1];
}
function absolute(base,value) {
    if(!value)return '';
    if(/^https?:\/\//i.test(value))return value;
    if(value.indexOf('//')===0)return 'https:'+value;
    return base+'/'+value.replace(/^\//,'');
}
function number(value) {
    var str=text(value).toUpperCase();
    var fc=str.match(/(?:^|[^A-Z0-9])FC2[-_ ]*(?:PPV[-_ ]*)?(\d{5,9})(?![A-Z0-9])/);
    if(fc)return 'FC2-PPV-'+fc[1];
    var match=str.match(/(?:^|[^A-Z0-9])([A-Z]{2,10})[-_ ]?(\d{2,7})(?![A-Z0-9])/);
    return match ? match[1]+'-'+match[2] : '';
}
function idFrom(url) {
    var path=String(url).replace(/^https?:\/\/[^/]+/i,'').split(/[?#]/)[0];
    if(SITE==='javdb') {var m=path.match(/^\/v\/([A-Za-z0-9_-]+)\/?$/);return m ? m[1] : '';}
    var part=path.replace(/^\//,'').replace(/\/$/,'');
    return /^[A-Za-z0-9_-]+$/.test(part) ? number(part) : '';
}
function checkPage(body) {
    if(/__cf_chl|challenge-running|Verifying you are human|<title[^>]*>\s*Just a moment|driver-verify|Access Denied/i.test(body))
        throw new Error('来源返回验证页或拒绝访问；请检查来源可用性与应用代理设置');
    if(!/<(?:html|body|div|a|h[123])\b/i.test(body))throw new Error('来源未返回可识别的 HTML 资料');
}
function firstImage(block,base) {
    var image=block.match(/<img\b[^>]*>/i);
    return image ? absolute(base,attr(image[0],'data-src')||attr(image[0],'src')) : '';
}
function dateIn(value) {var match=text(value).match(/\b((?:19|20)\d{2})[-/.](\d{2})[-/.](\d{2})\b/);return match ? match[1]+'-'+match[2]+'-'+match[3] : '';}
function metadata(id,title,url,code,poster) {
    var result={id:id,title:title,url:url,kind:'movie',external_ids:{}};
    if(code)result.external_ids.product_code=code;
    if(poster)result.poster=poster;
    return result;
}
function search(input,body,base) {
    var pattern=/<a\b[^>]*>[\s\S]*?<\/a>/gi,match,records=[],seen={};
    while((match=pattern.exec(body))!==null) {
        var block=match[0],opening=block.match(/^<a\b[^>]*>/i)[0],href=attr(opening,'href');
        if(SITE==='javbus' && !/(?:^|\s)movie-box(?:\s|$)/.test(attr(opening,'class')))continue;
        if(SITE==='javdb' && !/\/v\/[A-Za-z0-9_-]+/.test(href))continue;
        var id=idFrom(href);if(!id||seen[id])continue;
        var code=SITE==='javbus'?id:number(block);
        if(!code)continue;
        var image=block.match(/<img\b[^>]*>/i);
        var title=(image && attr(image[0],'title')) || attr(opening,'title');
        if(!title && SITE==='javdb') {var titleMatch=block.match(/<div\b[^>]*class=["'][^"']*video-title[^"']*["'][^>]*>([\s\S]*?)<\/div>/i);title=titleMatch?text(titleMatch[1]):'';}
        if(!title)title=text(block);
        if(!title)continue;
        if(title.toUpperCase().indexOf(code)<0)title=code+' '+title;
        var record=metadata(id,title,absolute(base,href),code,firstImage(block,base));
        var released=dateIn(block);if(released){record.released=released;record.year=parseInt(released.substr(0,4),10);}
        records.push(record);seen[id]=true;if(records.length>=100)break;
    }
    if(!records.length && !/movie-list|movie-box|movie-list-container|no results|沒有找到|没有找到|無搜尋結果|搜索結果|search results|搜尋結果|暫無影片|暂无影片/i.test(body))
        throw new Error('搜索页结构未识别，未将解析失败当作无结果');
    return records;
}
function labelValue(body,labels) {
    var pattern=new RegExp('<(?:p|div)\\b[^>]*>\\s*<(?:span|strong)\\b[^>]*>\\s*(?:'+labels+')\\s*[:：]?\\s*<\\/(?:span|strong)>([\\s\\S]*?)<\\/(?:p|div)>','i');
    var match=body.match(pattern);return match?text(match[1]):'';
}
function links(body,path) {
    var result=[],seen={},pattern=/<a\b[^>]*>[\s\S]*?<\/a>/gi,match;
    while((match=pattern.exec(body))!==null){
        var opening=match[0].match(/^<a\b[^>]*>/i)[0],href=attr(opening,'href');
        if(!path.test(href))continue;
        var name=text(match[0]);if(!name||name.length>200||seen[name])continue;
        result.push({name:name,url:href});seen[name]=true;
    }
    return result;
}
function detail(input,body,base) {
    var id=idFrom(input.url),heading=body.match(SITE==='javbus'?/<h3\b[^>]*>([\s\S]*?)<\/h3>/i:/<h2\b[^>]*class=["'][^"']*title[^"']*["'][^>]*>([\s\S]*?)<\/h2>/i);
    var title=heading?text(heading[1]):'';
    var code=number(labelValue(body,'識別碼|识别码|番號|番号|ID'))||number(title);
    if(!id||!title||!code||number(title)!==code)throw new Error('详情缺少一致的影片编号或标题，页面结构可能已变化');
    if(SITE==='javbus' && id!==code)throw new Error('详情编号与地址不一致');
    if(title.toUpperCase().indexOf(code)<0)title=code+' '+title;
    var cover=body.match(SITE==='javbus'?/<a\b[^>]*class=["'][^"']*bigImage[^"']*["'][^>]*>/i:/<img\b[^>]*class=["'][^"']*video-cover[^"']*["'][^>]*>/i);
    var poster=cover?absolute(base,attr(cover[0],SITE==='javbus'?'href':'src')):'';
    var result=metadata(id,title,input.url,code,poster);
    var released=dateIn(labelValue(body,'發行日期|发行日期|日期|Release Date'));
    if(released){result.released=released;result.year=parseInt(released.substr(0,4),10);}
    var description=body.match(/<meta\b[^>]*name=["']description["'][^>]*>/i);
    if(description){var overview=attr(description[0],'content');if(overview)result.overview=overview;}
    result.tags=links(body,SITE==='javbus'?/\/genre\//:/\/tags\//).map(function(row){return row.name;});
    result.actors=links(body,SITE==='javbus'?/\/star\//:/\/actors\//).map(function(row){return {name:row.name,gender:'unknown',aliases:[]};});
    result.directors=links(body,SITE==='javbus'?/\/director\//:/\/directors\//).map(function(row){return row.name;});
    result.studios=links(body,SITE==='javbus'?/\/studio\//:/\/makers\//).map(function(row){return row.name;});
    result.stills=[];var pattern=/<a\b[^>]*>/gi,match,seen={};
    while((match=pattern.exec(body))!==null){
        var tag=match[0],classes=attr(tag,'class');
        if(!/sample-box|tile-item/.test(classes))continue;
        var url=absolute(base,attr(tag,'href'));
        if(!/\.(?:jpg|jpeg|png|webp)(?:[?#]|$)/i.test(url)||seen[url])continue;
        result.stills.push(url);seen[url]=true;if(result.stills.length>=40)break;
    }
    return [result];
}
function buildRequest(input) {
    var base=origin(input);
    if(input.operation==='search') {
        var code=number(input.query);if(!code)throw new Error('请输入影片编号，例如 ABC-123 或 FC2-PPV-1234567');
        return {url:SITE==='javbus'?base+'/search/'+encodeURIComponent(code):base+'/search?q='+encodeURIComponent(code)+'&f=all'};
    }
    if(input.operation==='detail') {
        if(!idFrom(input.url))throw new Error('请输入此来源的影片详情页地址');
        return {url:input.url};
    }
    throw new Error('此来源只支持影片编号搜索和详情');
}
function parseResponse(input) {
    var body=String(input.body||'');checkPage(body);var base=origin(input);
    if(input.operation==='search')return search(input,body,base);
    if(input.operation==='detail')return detail(input,body,base);
    throw new Error('不支持的操作');
}
