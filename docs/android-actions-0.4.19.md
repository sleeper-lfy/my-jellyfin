# Android 0.4.19：Bilibili 风格页面实现

本版落实已确认的 21 屏设计，调整实际页面布局、信息密度和操作层级。首页、媒体库、个人中心、详情、队列、演员、片单、统计、连接、遥控、任务、更新以及播放器已使用新结构。设计预览使用的示例数量、人物和影片不写入生产数据。

版本 `0.4.19`，Android versionCode `36`，标签 `v0.4.19-preview.1`。测试与发布证据见 Release 附件及最终验证记录。

## 技术栈与拆分

保留现有 Java View 页面与 Compose 发现页，新增官方 `com.google.android.material:material:1.12.0`，不迁移接口或播放内核。

| 文件／组件 | 职责 |
| --- | --- |
| `MainActivity.java` | 页面路由、请求、查询范围、个人状态、手机队列与各页面数据 |
| `BiliMainUi.java` | 头像、真实数量栏、快捷入口、分组行、分类标签、演员网格与片单卡 |
| `BiliQueueAdapter.java` | 两行队列标题、拖动把手和无障碍操作说明 |
| `DiscoveryScreen.kt` 与已有小组件 | 搜索、来源、条件、排序、筛选抽屉、网格及状态 |
| `PlayerActivity.java`、`PlayerChrome.java` | 竖横屏控制布局、VR、分组设置；保留播放与手势状态机 |
| `BiliAuxiliaryUi.java` | 遥控、更新、电脑任务共用的轻量卡片与信息行 |
| `MediaStyle.java`、`NativeActionButton.java` | 官方原生 Material 按钮、触区、间距、Dialog 操作及海报收藏按钮 |
| `NativeBottomNavigation.java` | 官方四目的地底部导航 |
| `NativeActionTokens.kt`、`LumenTheme.kt` | Java 与 Compose 共用的颜色、字体、形状、间距语义角色 |

发现页直接使用 `LumenTheme`，与原生 token 桥接读取同一色板。共享样式和发现页验证深浅色；现有原生页面延续应用深色主题，未在本轮新增全局主题切换功能。

## 布局与交互

首页顶部只保留一处搜索，推荐与最近通过标签切换。紧凑续播卡使用具体文件的横向缩略图并完整适配画面，播放触区独立于图片，继续播放传递原 `file_id`。缩略图缺失时使用占位，不能用海报冒充。电影／VR 网格读取作品海报并保留固定 2:3 几何，加载失败不改变卡片布局。

媒体库保留七种分类，标签可横向滚动。发现页包含来源标签、单一搜索、横向可删除条件、结果数量、合并排序入口和两列网格。原有分页、搜索任务、来源选择、标签组合、演员、年份、评分、排除条件、刷新、错误重试与空状态保留；筛选仅在需要时弹出。收藏按钮的实际触区为 48dp，内部为 32dp 圆形 scrim，未选描边、已选实心，明暗照片下均校验对比度。

“我的”使用实际接口读取三项数量，未取得数据时显示占位或重试说明。四项快捷动作与分组设置行取代整页实心按钮。智能片单卡展示实际范围数量与最多三张作品海报；打开后仍由服务端按保存条件与当前查询求交集。统计采用实际播放数据，缺失字段显示“—”。演员头像绑定姓名，切换筛选不会混用另一位演员照片。

全局随机入口在首页与“我的”固定可见，具有六种独立范围；当前列表随机保留完整搜索／筛选／片单／发现结果范围。手机队列与电脑队列独立。拖拽排序与原有移动按钮均维护当前播放作品身份；标题请求迟到或已打开编辑器的队列被替换时，先校验队列快照，避免把旧内容写回。

竖屏播放器使用 16:9 视频窗口，普通播放保持原画面比例；横屏与 VR 保留全窗口渲染。右侧操作与底部快捷入口为轻图文动作，播放选项使用三个标签、分组行与直接切换的自动下一集。单击显隐、长按临时倍速、手势取消恢复、字幕、美颜、诊断、个人评价、时间书签、选集、队列、上下片、控制器与 VR 参数保留。加载／缓冲及错误具有可见反馈。截图中的风景是合成图，不能用来评估解码或网络性能。

电脑遥控只发送原有电脑控制命令；关机仍需确认且可取消。电脑任务保留分类、分页和只读语义，需在电脑执行的确认／重试不新增到手机。更新操作按真实状态出现，下载仍校验大小、摘要、包名、版本与签名，并通过系统确认安装。

## 控件规范与窗口

普通操作默认可见色面高 32dp、触控区域至少 48dp、圆角 8dp；卡片圆角 12dp。按钮使用官方 `MaterialButton`，选中／禁用由状态列表管理。轻操作使用透明色面，分组列表通过细分隔线表达层级。具有独立并列动作的区域使用 12dp 真实外部间距；换行及大字号允许自然增高。输入与正文遵循原有语义字体及 4dp 网格间距。

底部四项导航采用官方 `BottomNavigationView` 与紧凑指示器。滚动内容和导航分别测量，列表底部留出空隙；Dialog 操作保留独立间距。底部窗口读取可见区域并处理键盘与窗口尺寸变化，不挤掉滚动内容和末行文字。

## 验证和实际截图

新增测试直接构建实际 Activity／Dialog 或 Compose 页面，使用 MockWebServer 与合成图片，覆盖数据接口、全局与当前随机范围、真实按钮触摸、状态回滚、队列重排与快照保护、分页、窗口安全区、320dp 窄屏和 1.5 倍字号。旧测试改为操作真实标签、Chip 与分组行，保留原有行为断言。

本地完整 Android 回归 **226 项通过，零失败／错误／跳过**；lint 零错误（84 项提示），APK 构建通过。最终标签源码会在发布任务中重新验证完整回归、版本和签名。下列截图来自本轮真实组件绘制，未使用生成的设计图或旧版按钮图。

## 实际截图索引

以下为本轮实际渲染；全部使用虚构资料与合成图片。

| 页面 | 截图 |
| --- | --- |
| 首页与精确文件续播 | [查看](screenshots/android-actions-0.4.19/bilibili-main-home-393.png) |
| 媒体库七类导航与海报 | [查看](screenshots/android-actions-0.4.19/bilibili-main-library-393.png) |
| 我的：真实数量与分组入口 | [查看](screenshots/android-actions-0.4.19/bilibili-main-mine-393.png) |
| 发现：搜索、来源与排序 | [查看](screenshots/android-actions-0.4.19/bilibili-discovery-dark-393.png) |
| 发现：末行及底部安全区 | [查看](screenshots/android-actions-0.4.19/bilibili-discovery-dark-393-bottom.png) |
| 发现筛选抽屉 | [查看](screenshots/android-actions-0.4.19/bilibili-discovery-filter-dark-320-font150.png) |
| 影片详情 | [查看](screenshots/android-actions-0.4.19/bilibili-main-detail-393.png) |
| 全局随机范围 | [查看](screenshots/android-actions-0.4.19/bilibili-main-shuffle-393.png) |
| 手机队列与拖动排序 | [查看](screenshots/android-actions-0.4.19/bilibili-main-queue-393.png) |
| 竖屏播放器 | [查看](screenshots/android-actions-0.4.19/native-player-portrait.png) |
| 播放选项与自动下一集 | [查看](screenshots/android-actions-0.4.19/native-player-settings.png) |
| 横屏播放器 | [查看](screenshots/android-actions-0.4.19/native-player-landscape.png) |
| VR 播放工具 | [查看](screenshots/android-actions-0.4.19/native-player-vr.png) |
| 电脑遥控 | [查看](screenshots/android-actions-0.4.19/bili-remote-393.png) |
| 女演员墙 | [查看](screenshots/android-actions-0.4.19/bilibili-main-people-393.png) |
| 演员作品 | [查看](screenshots/android-actions-0.4.19/bilibili-main-actor-works-393.png) |
| 智能片单 | [查看](screenshots/android-actions-0.4.19/bilibili-main-playlists-393.png) |
| 观影统计 | [查看](screenshots/android-actions-0.4.19/bilibili-main-stats-393.png) |
| 连接管理 | [查看](screenshots/android-actions-0.4.19/bilibili-main-connection-393.png) |
| 电脑任务中心 | [查看](screenshots/android-actions-0.4.19/bili-tasks-393.png) |
| 客户端更新 | [查看](screenshots/android-actions-0.4.19/bili-update-393.png) |
| 媒体库筛选 | [查看](screenshots/android-actions-0.4.19/bilibili-main-filters-393.png) |
| 320dp／1.5倍字号：首页 | [查看](screenshots/android-actions-0.4.19/bilibili-main-home-320-font150.png) |
| 320dp／1.5倍字号：筛选 | [查看](screenshots/android-actions-0.4.19/bilibili-main-filters-320-font150.png) |
| 320dp／1.5倍字号：队列 | [查看](screenshots/android-actions-0.4.19/bilibili-main-queue-320-font150.png) |
| 320dp／1.5倍字号：发现 | [查看](screenshots/android-actions-0.4.19/bilibili-discovery-dark-320-font150.png) |
| 320dp／1.5倍字号：演员 | [查看](screenshots/android-actions-0.4.19/bilibili-main-people-320-font150.png) |
| 320dp／1.5倍字号：遥控 | [查看](screenshots/android-actions-0.4.19/bili-remote-320-font150.png) |
| 320dp／1.5倍字号：任务 | [查看](screenshots/android-actions-0.4.19/bili-tasks-320-font150.png) |
| 320dp／1.5倍字号：更新 | [查看](screenshots/android-actions-0.4.19/bili-update-320-font150.png) |
| 浅色主题：发现 | [查看](screenshots/android-actions-0.4.19/bilibili-discovery-light-393.png) |
| 浅色主题：末行安全区 | [查看](screenshots/android-actions-0.4.19/bilibili-discovery-light-393-bottom.png) |
