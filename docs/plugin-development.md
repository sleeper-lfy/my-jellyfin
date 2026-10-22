# 第三方刮削插件 API v1

插件目录含 `manifest.json` 与 `plugin.js`。设置 → 第三方插件 → 安装文件夹；安装前显示域名权限，安装后默认禁用。配置站点地址、分类、优先级、代理后启用。卸载只移除脚本与配置，不删已刮削资料。

核心不包含任何网站解析逻辑。例子：

- `plugins/example`：通用 JSON 影片目录协议；默认连接用户自己运行的本地目录服务；没有内置假影片。
- `plugins/tvmaze`：用户指定的优先站点；电视剧搜索、详情（含演员）、最新剧集索引发现。
- `plugins/internet-archive`：可选公开影片目录；只读取元数据和图片，不下载视频。

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

能力可选：`search`、`detail`、`discover`、`actors`。演员资料通常随 detail 返回；独立 actors 操作的传输接口可调用，但当前桌面没有单独演员资料抓取按钮。

## JavaScript 函数

```javascript
function buildRequest(input) {
    // input.operation, input.config, input.query / input.url / input.category
    return {url: input.config.base_url + '/catalog.json'};
}
function parseResponse(input) {
    // input.body, input.url, input.operation, input.content_type, input.config
    return JSON.parse(input.body).items;
}
```

每次 JS 调用是新进程/新引擎，无跨调用全局状态。可使用标准 JavaScript、JSON 和正则表达式；没有 Node.js、require、process、fetch、Python 桥接、文件系统或浏览器 DOM。复杂 HTML 解析应由脚本按目标协议实现，不向核心添加站点特例。

需要分页/详情/演员二次请求时，parseResponse 可返回：

```javascript
return {
  records: [],
  followups: [{url: 'https://catalog.example.org/detail/123'}]
};
```

宿主按同一权限和代理依序请求，URL 去重，每任务至多 20 个请求、1000 条记录、180 秒总预算（单次请求结束后检查预算）。JS 每次墙钟超时 8 秒；Linux CPU 7 秒/地址空间 768 MiB，Windows Job Object 768 MiB/父进程墙钟超时。超限进程被终止，错误进入任务列表。

普通响应最大 4 MB，图片 10 MB；单次 HTTP 读超时 20 秒，流读取预算 30 秒；保持 TLS 校验，不跟随 HTTP 重定向。站点需要跳转时配置最终域名和 URL，不能关闭校验。仅支持 GET；不支持任意自定义执行命令、视频资源下载或文件写入。

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

`id/title/url` 必填；kind 默认 movie，允许 movie/series/vr。year 为整数或 null，rating 为归一后的 0–10 来源评分或 null，绝不能写入用户个人评分。演员性别只能 female/male/unknown，缺失不推断。图片应落在 manifest 的域名列表内。本站不提供的日期/评分使用 null，不编造。

来源唯一键为 `(plugin,id)`；外部标识优先，标准化名称+年份+类型作为后备用于跨来源匹配。明确选择的本地作品可吸收对应未入库发现实体；若该来源已绑定另一部本地作品则停止，由用户核对。外部 IDs（如 IMDb）优先关联跨语言同一作品，历史名称与别名另有索引。不同作品恰好同名同年仍可能产生歧义；外部标识冲突时事务回滚，并可在详情中明确合并重复作品。没有共同外部标识时，不声称能自动解决所有同名歧义。

锁定字段不会被刷新覆盖；稀疏发现响应不会用空值清除既有演员/简介。所有来源保留各自评分、网址、更新时间、网站收录时间；软件首次发现时间独立保存。

## 代理和分类

设置默认代理为空表示直连；支持 `http://`、`https://`、`socks5://`、`socks5h://`。单插件 `inherit` 继承默认，空值强制直连。搜索、详情、演员附加请求、海报和演员图片走相同代理。TLS 校验开启，系统环境代理不自动覆盖用户显式的直连选择。

分类配置可逗号分隔，同脚本依次抓取各分类；发现页可按来源和分类过滤。TVmaze 默认/`latest` 从公共更新索引中取最新分配的 12 个剧集 ID，再获取含演员的详情；数字分类对应站点索引页。**ID 顺序不是网站收录日期**：TVmaze 不提供该日期时保存 null；上映日期取 premiered，首次发现为本地时间戳。推荐不冒充最新排序。Internet Archive 分类为 collection 名，默认 feature_films。

## 运行验证

```powershell
.venv\Scripts\python -m pytest -q tests/test_plugins.py tests/test_extended.py
```

测试使用真实本地 HTTP 服务和明确标注的协议测试记录，验证隔离、域名控制、解析、来源去重、锁定及失败日志。产品空库没有演示数据。云环境真实站点访问受网络策略限制时，记录 403，不能用协议测试代替在线成功。

要新增站点：复制示例 → 改 ID/域名/请求与解析函数 → 加响应 fixture 测试 → 安装查看权限 → 配置/启用 → 用实际网址验证。无需修改主程序。

## 剧照与下载

`stills` 为可选的 HTTP/HTTPS 图片 URL 数组，最多 40 张；不提供时省略或返回空数组。图片域名必须声明在 manifest 中，复用插件代理和网络权限。主程序校验图片并缓存，详情页保持比例展示；失败项记录任务，元数据仍可入库。相同 URL 的已缓存剧照不会重复下载。插件不应返回 `stills_cache` 等内部缓存路径。TVmaze 详情请求同时嵌入 images，取站点提供的 background 图片；站点没有图片就保持空列表。

`download_method` 为 `magnet` 或 `direct`；`download_url` 为最多 40 项的对象数组，每项包含 `url`、可选 `method` 和 `description`。单项 method 优先，省略则继承顶层方式。支持混合磁力与直链资源，方式与 URL 协议必须匹配。只返回网站提供的真实链接，不编造大小、清晰度或字幕说明。

Windows 磁力按钮交给系统关联的下载器（例如已关联 magnet 的迅雷）；不会强制安装或默认绑定下载器。HTTP/HTTPS 直链由桌面端流式下载，用户选择保存位置后启动，使用插件域名白名单和代理，不将整部视频载入内存。下载期间显示字节进度，取消或失败删除临时文件，成功后才发布最终文件；原文件不会因下载失败损坏。重定向不自动跟随，插件应返回声明域名内的最终直链。安卓磁力与直链按钮交由系统支持的应用处理。下载信息和剧照均可通过已认证的局域网接口读取；本地缓存路径不暴露给客户端。

### 发现页的详情资源加载（0.4.1）

发现列表可以只返回基本资料；打开详情页时，主程序会使用已保存的来源 URL 调用对应插件的 `detail`，并要求返回的 `id` 与该来源 `source_id` 精确一致，随后缓存 `stills` 并显示 `download_url`。自动详情刷新每小时至多一次；用户可点击“刷新剧照与下载资源”立即重试。未入库影片也能查看与下载，下载仅在点击资源时启动。示例 JSON 插件 1.1.0 已透传这三个可选字段；安装过旧示例插件的用户需更新插件脚本。
