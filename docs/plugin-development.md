# 第三方刮削插件 API v1

插件目录含 `manifest.json` 与 `plugin.js`。设置 → 第三方插件 → 安装文件夹；安装前显示域名权限，安装后默认禁用。配置站点地址、分类、优先级、代理后启用。卸载只移除脚本与配置，不删已刮削资料。

核心不包含任何网站解析逻辑。例子：

- `plugins/example`：通用 JSON 影片目录协议；默认连接用户自己运行的本地目录服务；没有内置假影片。
- `plugins/tvmaze`：用户指定的优先站点；电视剧搜索、详情（含演员）、最新剧集索引发现。
- `plugins/internet-archive`：可选公开影片目录；只读取元数据和图片，不下载视频。
- `plugins/wikimedia-actors`：独立女演员头像搜索，Wikidata 女性人物 + Wikimedia Commons 公开肖像；保留文件页、许可和署名。没有照片或资料的演员不会编造头像。
- `plugins/javbus-actors`：按姓名搜索 JavBus 女优头像；只读取公开姓名、别名与图片地址，不返回视频或下载链接。默认声明 `www.javbus.com` / `javbus.com` / `r.jina.ai`，直连被站点浏览器验证拦截时自动经 r.jina.ai 读取；头像许可与署名以来源页面为准，插件不编造。
- `plugins/javdb-actors`：按姓名搜索 JavDB 演员资料，读取公开头像和逗号分隔的别名；占位头像不当作真实头像，`gender` 不据姓名推断。只读取元数据与头像，不返回视频、磁力或下载链接。部分网络需在应用内配置代理。
- `plugins/javrate-actors`：按姓名搜索 JavRate 女优资料，默认经 `r.jina.ai` 绕过站点的 Cloudflare 验证，读取公开头像并将列表 `_s.webp` 升级为同目录 `_l.webp` 大图；只读取元数据与头像，不返回视频、磁力或下载链接。Reader 需要应用内配置可用代理。

## manifest.json

```json
{
  "api_version": 1,
  "id": "my-site",
  "name": "我的站点",
  "version": "1.0.0",
  "description": "元数据提供者",
  "capabilities": ["search", "detail", "discover"],
  "domains": ["catalog.example.org", "images.example.org"],
  "base_url": "https://catalog.example.org"
}
```

ID 为小写字母开头的 2–51 位字母、数字、连字符。`domains` 为精确主机名（无协议、端口、路径、通配符）；只有这些地址可由宿主请求。插件安装后无法通过 JS 扩大权限；改权限需卸载重装并查看新声明。

能力可选：`search`、`detail`、`discover`、`actors`。演员资料可以随 detail 返回，也可以实现独立 `actors` 搜索；独立演员记录使用下文格式，不是影片记录，不会创建一部同名影片。

影片站点的在线搜索另可声明 `"search_filters": ["name", "tag"]`；未声明时按仅支持 `name` 处理。名称通过 `buildRequest(input).query` 传入，标签通过 `input.tag` 传入；两者同时填写时来源应真正将两个条件组合到站点查询。不要把 `discover` 的最新列表冒充搜索结果，也不要将不支持的标签参数忽略。内置 TVmaze 仅有名称搜索，填写站点标签时会明确显示不支持；Internet Archive 1.1.0 使用 Advanced Search 的 `title:"名称"` 与 `subject:"标签"` 条件，支持名称、标签或同时检索。站点支持标签搜索，与对已发现资料做本地标签筛选是两种功能。

`search_sites(library, query, tag='', plugin_id='', progress=None)` 顺序调用已启用的搜索来源。结果包含 `ids/count/added/matched/local_matches/searched/errors`，每个来源错误为 `{plugin,name,message}`。至少一个来源成功时返回可用结果及部分错误；所有来源失败或均不支持所填条件时抛出带 `.result` 的 `DiscoverySearchError`，不会显示“搜索成功，0 条”。重试会创建新的独立任务。

检索只保存未入库的发现资料。来源 ID、外部 ID 或标题与年份关联到本地影片时保留该作品 ID 作为命中，不执行资料、海报、个人评分或播放进度更新。保存前在短事务内重新检查本地关联，避免扫描导入同时进行时覆盖本地资料；Fans 和其他视频不能作为影视刮削目标。搜索不下载视频、不启动播放，也不逐条下载演员图和剧照。海报 URL 留在元数据中，由可见项按需加载小预览；每次图片请求都复用来源权限和代理，HTTP 请求不持有数据库写锁。

局域网客户端使用鉴权异步接口：

- `GET /api/discovery/providers` → `{items:[{id,name,supports_tags,search_filters}]}`，只列已启用且支持 search 的来源。
- `POST /api/discovery/search`，正文 `{query,tag,plugin}` → `202 {task_id}`；名称与标签不能同时为空。`plugin` 留空表示所有已启用搜索来源。
- `GET /api/discovery/search/{task_id}` → `{id,kind,status,payload,result,error,updated}`，状态为 queued/running/done/failed/cancelled。`result.ids` 可传给 `/api/discover?ids=...` 精确显示本次命中；明确空的 ids 集合不会变成所有发现资料。

在线任务共用应用的后台并发预算，局域网站点搜索另限一个工作线程及最多四个未完成任务；队列满返回 429。任务状态通过现有 TaskJournal 异步写入，资料库读取和操作不会等待搜索的 HTTP 请求。未完成任务被关闭服务中断后可重新发起，错误不会被当作正常空结果。

已安装旧版 Internet Archive 的用户可在 PC 发现面板明确执行“安装 / 更新站点来源”，无需卸载。界面先显示 TVmaze 或 Internet Archive 的完整域名权限，再从当前应用随附目录更新；已有代理、分类、启用状态、优先级及其他配置全部保留。底层 `builtin_search_plugin(id)` / `update_builtin_search_plugin(id)` 只接受 `tvmaze`、`internet-archive`，不能更新任意第三方插件，也不会自动启用新安装的插件。界面的“更新并启用”是用户选择后的独立配置动作；Android 可提示在 PC 配置来源。不会后台自动升级或扩大第三方来源权限。

## JavaScript 函数

```javascript
function buildRequest(input) {
    // input.operation, input.config, input.query / input.url / input.category
    return {url: input.config.base_url + '/catalog.json'};
}
function parseResponse(input) {
    // input.body, input.url, input.operation, input.content_type, input.config, input.context
    return JSON.parse(input.body).items;
}
```

每次 JS 调用是新进程/新引擎，无跨调用全局状态。可使用标准 JavaScript、JSON 和正则表达式；没有 Node.js、require、process、fetch、Python 桥接、文件系统或浏览器 DOM。复杂 HTML 解析应由脚本按目标协议实现，不向核心添加站点特例。

需要分页/详情/演员二次请求时，parseResponse 可返回：

```javascript
return {
  records: [],
  followups: [{url: 'https://catalog.example.org/detail/123', context: {source_id: '123'}}]
};
```

宿主按同一权限和代理依序请求，URL 去重，每任务至多 20 个请求、1000 条记录、180 秒总预算（单次请求结束后检查预算）。JS 每次墙钟超时 8 秒；Linux CPU 7 秒/地址空间 768 MiB，Windows Job Object 768 MiB/父进程墙钟超时。超限进程被终止，错误进入任务列表。

`context` 可选，为后续请求携带 JSON 上下文；宿主将其作为该次 `parseResponse(input).context` 传回。上下文不提供额外权限，也不参与 URL 去重；同一 URL 仍只请求一次。Wikimedia 插件用它将人物标识与 Commons 图片解析结果关联，每次任务至多搜索 6 个候选，保持在上述预算内。

普通响应最大 4 MB，图片 10 MB；单次 HTTP 读超时 20 秒，流读取预算 30 秒；保持 TLS 校验，只跟随声明域名内最多 3 次重定向，跨域跳转拒绝。站点需要跳到未声明域名时配置最终域名和 URL，不能关闭校验。仅支持 GET；不支持任意自定义执行命令、视频资源下载或文件写入。

宿主优先调用系统 `curl` 发送插件请求（Windows 10/11 自带，Linux/macOS 通常已安装），没有 curl 时回退 httpx。使用 curl 是为了兼容按 TLS 指纹拦截 Python 客户端的站点；两种方式共用相同的精确域名、协议、代理、TLS 校验、大小和请求预算，curl 不跟随重定向，跳转仍由宿主逐次校验。宿主请求携带常见浏览器的 `User-Agent`、`Accept` 和 `Accept-Language`，不执行交互式验证。

## 标准影片记录

```json
{
  "id": "site-id",
  "title": "影片名称",
  "kind": "movie",
  "year": 2024,
  "released": "2024-01-01",
  "site_added": null,
  "url": "https://catalog.example.org/detail/site-id",
  "aliases": ["别名"],
  "overview": "简介",
  "tags": ["剧情"],
  "directors": ["导演"],
  "actors": [{"id":"provider:actor-id","name":"演员","aliases":[],"gender":"female","photo":"https://images.example.org/a.jpg"}],
  "poster": "https://images.example.org/poster.jpg",
  "stills": ["https://images.example.org/still-1.jpg"],
  "download_method": "magnet",
  "download_url": [
    {"url":"magnet:?xt=urn:btih:0123456789012345678901234567890123456789","method":"magnet","description":"4.5GB · 3 个文件 · 高清/中字"},
    {"url":"https://downloads.example.org/video.mp4","method":"direct","description":"HTTP 直链"}
  ],
  "rating": 8.1,
  "external_ids": {"imdb":"tt1234567"}
}
```

`id/title/url` 必填；kind 默认 movie，允许 movie/series/vr。year 为整数或 null，rating 为归一后的 0–10 来源评分或 null，绝不能写入用户个人评分。插件演员性别只能 female/male/unknown；无资料时返回 unknown，不编造。主程序按用户要求将电影及 VR 电影的未知性别默认按女性处理，电视剧保留 unknown。图片应落在 manifest 的域名列表内。本站不提供的日期/评分使用 null，不编造。

来源唯一键为 `(plugin,id)`；外部标识优先，标准化名称+年份+类型作为后备用于跨来源匹配。明确选择的本地作品可吸收对应未入库发现实体；若该来源已绑定另一部本地作品则停止，由用户核对。外部 IDs（如 IMDb）优先关联跨语言同一作品，历史名称与别名另有索引。不同作品恰好同名同年仍可能产生歧义；外部标识冲突时事务回滚，并可在详情中明确合并重复作品。没有共同外部标识时，不声称能自动解决所有同名歧义。

锁定字段不会被刷新覆盖；稀疏发现响应不会用空值清除既有演员/简介。所有来源保留各自评分、网址、更新时间、网站收录时间；软件首次发现时间独立保存。

## 独立演员头像

调用 `Plugins.run(plugin_id, 'actors', query='演员姓名')`。`buildRequest` 的 `operation` 为 `actors`，`query` 为输入姓名；`parseResponse` 直接返回候选数组或 `{records, followups}`。每个候选示例：

```json
{
  "id": "provider:person-123",
  "name": "演员姓名",
  "gender": "female",
  "aliases": ["另一种拼写"],
  "url": "https://catalog.example.org/people/123",
  "photo": "https://images.example.org/people/123.jpg",
  "photo_page": "https://images.example.org/people/123",
  "photo_license": "CC BY-SA 4.0",
  "photo_attribution": "摄影者姓名"
}
```

`id/name/url` 必填，`photo` 允许缺省或 null；没有头像的候选不能用于更新。`gender` 为 female/male/unknown；`aliases` 为至多 100 个姓名。头像和元数据请求遵守 manifest 精确域名、代理、TLS、大小和时间限制。内置 TVmaze 1.2.0 新增 `/search/people` 搜索；Wikimedia 插件使用 Wikidata `wbsearchentities`、`wbgetentities` 以及 Commons `imageinfo`，只返回已声明为女性人物且有公开肖像的候选。站点搜索结果可能包含同名人物，必须由用户确认，不按首条结果自动替换。

JavBus 插件（`javbus-actors`）请求 `/searchstar/<姓名>`，优先解析搜索结果中的头像；结果只有演员链接时再逐条请求演员页读取头像，每次任务最多返回 12 个候选。站点把搜索重定向到唯一演员页时，插件会按演员页解析；直连被站点浏览器验证（`/doc/driver-verify`）拦截时，自动改为经 `r.jina.ai`（第三方 Reader 服务，有频率限制）读取同一地址并解析其 Markdown 输出，验证页再次出现时如实报错。它只返回头像地址和来源页，不提供许可或署名，界面不会补造这些字段。宿主只跟随声明域名内的有限重定向；跨域跳转、需要登录或站点换到未声明域名时须在插件配置中填写最终地址，否则如实失败。该来源只用于元数据与头像，不返回视频、磁力或下载链接。

JavDB 插件（`javdb-actors`）请求 `/search?f=actor&q=<姓名>`，解析演员卡片的 `/actors/<id>`、`<strong>` 姓名、`title` 中的逗号分隔别名和 `c0.jdbstatic.com` 头像。`actor_unknow` 占位图不会当作真实头像，候选仍返回但 `photo` 为空；来源没有性别字段，`gender` 保存为 `unknown`，不从姓名推断。JavDB 在部分网络下直连超时或被 TLS 指纹拦截，需在应用设置中配置代理（环境变量不生效）；Cloudflare 挑战页会明确报错，不伪造结果。

JavRate 插件（`javrate-actors`）请求 `/actor/list/<姓名小写>`，默认经 `r.jina.ai` 转发并解析其 Markdown：只读取“共找到AV女優”到“查找:”之间的结果卡片，排除“本月出道女優”等侧栏；卡片提供 `/actor/detail/<id>.html`、姓名和 `picture.avking.xyz` 头像。列表用的 `_s.webp` 会升级为同目录 `_l.webp`（实测 800×1280 到 1920×2882），比 JavDB 的 200×200 头像清晰。0 结果返回空；Reader 限流、Cloudflare 拦截或需要代理时会明确报错，不伪造候选。`r.jina.ai` 为第三方只读转发服务，搜索请求会经过它。

确认后调用 `Plugins.merge_actor(plugin_id, candidate, actor_name, replace=False)`，其中 `actor_name` 是本地演员姓名或本地别名。默认补充缺失缓存，`replace=True` 覆盖已有头像；更新该姓名在全库未锁定演员字段中的所有匹配项，保留原演员姓名、别名、其他影片资料。锁定 `actors` 的作品始终跳过。下载及解码在数据库写事务之前进行，并在写入时重新读取资料，避免网络慢时锁住其他写入或覆盖期间的人工编辑。图片按比例缩小到最长边 1200 后缓存。返回 `{updated, skipped, name}`。

本地数据保留 `photo_source/photo_source_id/photo_source_url`，以及来源提供的 `photo_page/photo_license/photo_attribution`。Commons 文件的许可各不相同，使用图片时应同时保留署名及许可来源。头像缓存以图片内容 SHA-256 命名，`photo_revision` 保存该内容散列。局域网详情 `actors[].photo` 返回带内容修订参数的鉴权缓存地址 `/api/works/{work_id}/actors/{index}/photo?v=内容散列`；同一个来源 URL 的图片被更新时，手机会加载新图片而非命中旧头像缓存。生成详情响应不读取图片文件。不暴露本地路径；缓存目录之外的文件拒绝读取。

旧安装的 TVmaze 清单没有 `actors` 能力。在女演员墙点击“刮削演员头像…”或影片详情的“更多操作 → 刮削演员头像…”，再点击“安装 / 更新内置头像来源…”，选择页面列出的来源与域名权限后会安装、更新并启用该来源，保留代理和其他配置。底层 `update_builtin_actor_plugin` 方法只更新文件，不自行启用；在设置中手工安装文件夹仍需手工启用。第三方插件不会被后台自动升级或覆盖。

云开发环境对这些公开站点的请求当前被网络代理拒绝，独立演员流程已通过官方响应结构的本地回归测试；该环境未完成真实站点连通验证。站点没有照片、网络阻断或受地区限制时会显示失败，不伪造成功。

## 代理和分类

设置默认代理为空表示直连；支持 `http://`、`https://`、`socks5://`、`socks5h://`。单插件 `inherit` 继承默认，空值强制直连。搜索、详情、演员附加请求、海报和演员图片走相同代理。TLS 校验开启；系统环境代理不自动覆盖用户显式的直连选择，`HTTP_PROXY` 等环境变量对宿主请求不生效，需在应用内配置代理。宿主请求携带常见浏览器的 `User-Agent`、`Accept` 与 `Accept-Language` 头，以兼容按客户端特征拦截的站点；宿主不执行站点的交互式验证，验证页会如实失败。

分类配置可逗号分隔，同脚本依次抓取各分类；发现页可按来源和分类过滤。TVmaze 默认/`latest` 从公共更新索引中取最新分配的 12 个剧集 ID，再获取含演员的详情；数字分类对应站点索引页。**ID 顺序不是网站收录日期**：TVmaze 不提供该日期时保存 null；上映日期取 premiered，首次发现为本地时间戳。推荐不冒充最新排序。Internet Archive 分类为 collection 名，默认 feature_films。

## 运行验证

```powershell
.venv\Scripts\python -m pytest -q tests/test_actor_plugins.py tests/test_plugins.py tests/test_extended.py
```

测试使用真实本地 HTTP 服务和明确标注的协议测试记录，验证隔离、域名控制、解析、来源去重、锁定及失败日志。产品空库没有演示数据。云环境真实站点访问受网络策略限制时，记录 403，不能用协议测试代替在线成功。

要新增站点：复制示例 → 改 ID/域名/请求与解析函数 → 加响应 fixture 测试 → 安装查看权限 → 配置/启用 → 用实际网址验证。无需修改主程序。

## 剧照与下载

`stills` 为可选的 HTTP/HTTPS 图片 URL 数组，最多 40 张；不提供时省略或返回空数组。图片域名必须声明在 manifest 中，复用插件代理和网络权限。主程序校验图片并缓存，详情页保持比例展示；失败项记录任务，元数据仍可入库。相同 URL 的已缓存剧照不会重复下载。插件不应返回 `stills_cache` 等内部缓存路径。TVmaze 详情请求同时嵌入 images，取站点提供的 background 图片；站点没有图片就保持空列表。

`download_method` 为 `magnet` 或 `direct`；`download_url` 为最多 40 项的对象数组，每项包含 `url`、可选 `method` 和 `description`。单项 method 优先，省略则继承顶层方式。支持混合磁力与直链资源，方式与 URL 协议必须匹配。只返回网站提供的真实链接，不编造大小、清晰度或字幕说明。

HTTP/HTTPS 直链由电脑服务端流式下载，使用插件域名白名单和代理；下载完成后关联当前作品，补充 NFO、海报和剧照。电影、电视剧、VR 电影各有默认目录，用户仅在需要时更改。qBittorrent 可接收磁力和目标目录；系统 magnet 通用协议不携带目录，其他下载器需自行确认保存位置或配置自定义命令。外部工具完成后由用户点击检查入库。Android 点击资源同样交给电脑服务端处理，并显示下载进度。实现与接口见 [下载与入库](downloads.md)。

### 发现页的详情资源加载（0.4.1）

发现列表可以只返回基本资料；打开详情页时，主程序会使用已保存的来源 URL 调用对应插件的 `detail`，并要求返回的 `id` 与该来源 `source_id` 精确一致，随后缓存 `stills` 并显示 `download_url`。自动详情刷新每小时至多一次；用户可点击“刷新剧照与下载资源”立即重试。未入库影片也能查看与下载，下载仅在点击资源时启动。示例 JSON 插件 1.1.0 已透传这三个可选字段；安装过旧示例插件的用户需更新插件脚本。
