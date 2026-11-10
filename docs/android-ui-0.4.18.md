# Android UI 与海报修复：0.4.18

本版包含实际首页／媒体库的电影与 VR 海报修复，以及用户确认后的第一阶段 UI 基础组件。新基础层尚未接入其他整页；这里的组件预览不表示所有现有页面已经采用新布局。Android 版本为 `0.4.18`，versionCode 为 `34`，预发布目标标签为 `v0.4.18-preview.1`。

## 实际页面的图片规则

| 位置 | 使用的图片 | 展示及缺图规则 |
| --- | --- | --- |
| 首页最近入库：电影、VR | 真正的作品海报 | 2:3 区域，居中裁切铺满；无海报或加载失败显示占位 |
| 媒体库：电影、VR | 真正的作品海报 | 同上，加载前后保持图片和卡片尺寸稳定 |
| 继续观看 | 当前续播视频文件的指定缩略图 | 保持横向区域，完整等比显示；不回退作品海报 |
| 其他现有分类 | 沿用原有规则 | 本次没有借海报修复统一改写其他分类 |

海报与视频缩略图具有不同用途。电脑服务端统一选择作品海报，Android 再按电影／VR 卡片规则显示；仅在手机上更换裁切方式不能修复服务端返回错误图片的问题。旧服务端封面字段混用了海报与缩略图，即使原来的电脑和手机版本一致，也可能复现错误，因此验证本次修复需要同时更新两端。

缺图卡片保留可辨识的占位和无障碍说明；加载失败不会改变 2:3 区域，也不会把视频缩略图填进作品海报位置。继续观看另行验证了视频缩略图请求，不借用作品海报请求。

## 第一阶段基础组件

本阶段新增独立的 `net.lumen.media.ui.theme` 与 `net.lumen.media.ui.components`，使用项目已有的 Compose Material 3。颜色、字体和形状来自 `LumenTheme`；页面间距通过 `LocalAppSpacing` 读取，固定语义尺寸通过 `AppDimensions` 读取。深浅主题预览及组件样例不调用资料库、网络、播放器或业务导航。

| 项目 | 已实现规则 |
| --- | --- |
| 间距 | 4／8／12／16／24dp，页面边距 16dp，同排操作间距 12dp |
| 普通操作按钮 | 官方主按钮、次按钮、危险按钮和文字按钮；视觉最小高度 32dp，实际触控区域至少 48×48dp |
| 按钮内容 | 横向 8dp、纵向 4dp 内边距，图标 18dp、图文间距 4dp；文字放大时自然增高，未固定最大高度 |
| 圆角 | 普通按钮 8dp；海报／卡片 12dp；底部抽屉 16dp；Chip 与独立收藏按钮保留圆形或胶囊形 |
| Chip | 官方 FilterChip／InputChip，视觉 32dp，触控至少 48dp；中性选中容器与勾选图标，输入 Chip 支持删除 |
| 字体 | 页面标题 22sp、分区标题／正文 16sp、辅助正文 14sp、标签与副信息 12sp，统一使用主题字体角色 |
| 图片卡片 | 官方 Card；图片固定 2:3，Crop；骨架 shimmer、失败占位与图片保持同一几何区域 |
| 收藏 | 独立 48dp 操作，深色半透明圆底；选中实心、未选描边；点击不触发卡片详情 |
| 其他基础件 | 统一图标、搜索与建议、官方导航和模态底部抽屉；深浅主题分别预览 |

32dp 指普通字号下的按钮可见色面，不是把可点击区域缩到 32dp。外层为官方按钮预留至少 48dp，保留 Material 的点击扩展及单一点击语义；按钮内部不重复增加点击处理。放大字体后，色面可以超过 32dp，以保证文字完整。

这些规范目前约束新增基础组件。截图中的实际首页／媒体库仍属于现有页面，不能据此认定其按钮、导航和全部留白已经迁移；其本轮变化仅为约定的电影／VR 海报展示。

## 已验证与待验证

Android 本地完整测试共 183 项，失败、错误、跳过均为 0；lint 为 0 错误、67 条警告；Debug APK 构建成功。测试包含实际 HTTP 图片请求、原生 View 布局与 Compose 组件，不把 HTML 画廊当作 App 布局测试。

`PosterPresentationTest` 验证电影／VR 作品使用对应海报、加载失败和缺图的卡片尺寸不变、其他分类的显示方式保留，以及继续观看只请求指定视频文件缩略图。基础层测试验证深浅主题、普通按钮的 32dp 视觉和至少 48dp 触控、视觉外缘的真实点击、禁用按钮不执行操作、窄屏大字文本不裁切等情况。

电脑端海报、图片角色、发现卡片异步加载、LAN 封面与续播相关 135 项回归通过，完整 Python 收集 839 项。Windows 云端全量构建与安装／卸载验收、发布 CI、签名及公开下载检查待执行。截图与自动测试也不能证明小米 15 的 HEVC 4K 卡顿已经解决，仍需实机持续播放和拖动验证。

## 实际页面截图

以下 5 张图来自原生 Android 实际布局与 HTTP 测试素材，作品名称及海报均为虚构，不包含用户图片。

| 场景 | 截图 |
| --- | --- |
| 首页继续观看使用视频缩略图 | [查看](screenshots/android-ui-0.4.18/poster-home-continue-thumbnail.png) |
| 首页最近入库：电影与 VR 海报 | [查看](screenshots/android-ui-0.4.18/poster-home-recent-movie-vr.png) |
| 媒体库电影 | [查看](screenshots/android-ui-0.4.18/poster-library-movie.png) |
| 媒体库 VR | [查看](screenshots/android-ui-0.4.18/poster-library-vr.png) |
| 无海报／加载失败占位 | [查看](screenshots/android-ui-0.4.18/poster-library-unavailable.png) |

## 第一阶段组件截图

以下 8 张图来自新基础组件的原生预览。宽幅总览用于比较完整组件，手机截图用于检查实际窗口中的留白、滚动和底部安全区；它们不冒充已迁移的业务页面。

| 场景 | 深色 | 浅色 |
| --- | --- | --- |
| 全组件总览 | [查看](screenshots/android-ui-0.4.18/design-system-stage1-dark.png) | [查看](screenshots/android-ui-0.4.18/design-system-stage1-light.png) |
| 手机预览：文字、紧凑按钮与 Chip | [查看](screenshots/android-ui-0.4.18/design-system-phone-dark.png) | [查看](screenshots/android-ui-0.4.18/design-system-phone-light.png) |
| 手机预览：卡片与底部操作 | [查看](screenshots/android-ui-0.4.18/design-system-phone-dark-bottom.png) | [查看](screenshots/android-ui-0.4.18/design-system-phone-light-bottom.png) |
| 底部抽屉 | [查看](screenshots/android-ui-0.4.18/design-system-sheet-dark.png) | [查看](screenshots/android-ui-0.4.18/design-system-sheet-light.png) |
