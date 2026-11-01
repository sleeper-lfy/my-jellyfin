"""Publish a Gitee release for the staged artifacts; token comes from the local file or env."""
import hashlib
import os
import sys
from pathlib import Path
import httpx

REPO = 'sleeper_lfy/my-jellyfin'
TAG = 'v0.4.13'
NAME = 'Lumen 0.4.13（Windows + Android）'
PRERELEASE = False
TARGET = 'main'
ASSETS = ['Lumen-Setup-x64.exe', 'Lumen-Setup-x64.exe.sha256', 'Lumen-android-debug.apk', 'Lumen-android-debug.apk.sha256']

BODY = '''测试预发布，面向愿意试用的用户；真机音频、DPI、旧版升级与真实插件站点仍未验证，完成验收后会在 GitHub 发布正式版并同步本站。

相对 v0.4.12-preview.1 的变化：

- 更新检测与安装包下载切换到 Gitee Releases，PC 支持分卷安装包下载后合并校验，不再依赖 GitHub
- Windows 安装包不再捆绑 FFmpeg：启动时引导使用本机 FFmpeg（配置目录 / PATH），或联网自动下载一次（SHA-256 锁定的 gyan.dev essentials 9.0.2）
- 安装包移除内嵌 WebEngine（Chromium）等未使用的 Qt 模块（192MB → 84MB），功能不受影响
- APK 仅保留 ARM 架构（96MB → 47MB）；x86 架构仅模拟器使用
- 右键菜单新增“删除本地文件”：列出清单、确认后删除视频及同名字幕 / NFO / 图片并移出媒体库；文件离线或播放中时中止
- 批量拖入文件夹可统一选择刮削器与整理目标目录，自动匹配默认采用搜索到的第一个结果（优先精确匹配）
- 播放控制栏新增“增强 / 美颜”一级开关（PC），Android 播放栏新增“美颜”按钮
- 安卓布局修复：我的媒体磁贴均分不再变形，密集按钮行边距恢复正常

验证范围：PC 452 项自动化测试、Android 77 项测试通过；Windows 安装包完成安装 / 卸载自动验收（UI、播放运行时、插件工作进程、安装与卸载）。真机听感、全屏、DPI、旧版升级和真实插件站点未验证。Android versionCode 16，与 preview.1 使用同一持久签名，可直接覆盖安装。

相对 0.4.12 的变化：

- 查询层 SQL 化：筛选与分页下推 SQLite，大库分页提速约 20 倍
- 手机端新增女演员墙与高级筛选（年份范围/评分下限/多标签组合）
- 媒体库自动巡检：分批后台检测缺失/重命名/新增，离线盘自动跳过
- 详情页"扫描本地文件变化"与右键移除季集记录（保留磁盘文件）
- 右键"删除本地文件"（清单确认后删除并移出媒体库）
- 海报/缩略图支持选择本地图片（文件选择或拖入对话框）
- 导入对话框可选刮削器与整理目标，批量拖入按相同设置依次入队，自动匹配默认取第一个结果
- 更新渠道切换到 Gitee；安装包不再捆绑 FFmpeg（启动时引导配置或联网下载）
- 修复文件夹拖入间歇失效、目录选择器白字白底、安卓磁贴与密集按钮行变形

SHA-256：

SHA-256：

- Lumen-Setup-x64.exe：70c880f73b1874e2599a6a7b9a420b6867a4f0e5703a090e1e903d35e16127e2（单文件 84MB）
- Lumen-android-debug.apk：632d579e10b851fff793b498c58d17430c8b73a08048fb9dfde44d1e45e69745'''


def token():
    value = os.environ.get('GITEE_TOKEN') or ''
    if not value:
        path = Path(__file__).resolve().parents[1] / '.local' / 'gitee-token.txt'
        if path.is_file():
            value = path.read_text(encoding='utf-8').strip()
    if not value:
        raise SystemExit('缺少 Gitee 令牌：请保存到 .local/gitee-token.txt 或设置 GITEE_TOKEN')
    return value


def main():
    access = token()
    root = Path(__file__).resolve().parents[1] / 'target'
    with httpx.Client(timeout=60) as client:
        existing = client.get(f'https://gitee.com/api/v5/repos/{REPO}/releases/tags/{TAG}', params={'access_token': access})
        if existing.status_code == 200 and existing.json():
            release = existing.json()
            print('Release 已存在，复用：', release['id'])
        else:
            created = client.post(f'https://gitee.com/api/v5/repos/{REPO}/releases', json={
                'access_token': access, 'tag_name': TAG, 'name': NAME, 'body': BODY,
                'target_commitish': TARGET, 'prerelease': PRERELEASE})
            if created.status_code >= 300:
                raise SystemExit(f'创建 Release 失败：{created.status_code} {created.text[:400]}')
            release = created.json()
            print('Release 已创建：', release['id'])
        identifier = release['id']
        uploaded = {asset['name'] for asset in release.get('assets', [])}
        for name in ASSETS:
            if name in uploaded:
                print('已存在附件，跳过：', name)
                continue
            path = root / name
            data = path.read_bytes()
            print(f'上传 {name}（{len(data) / 1048576:.1f} MB）…')
            attached = client.post(
                f'https://gitee.com/api/v5/repos/{REPO}/releases/{identifier}/attach_files',
                params={'access_token': access}, files={'file': (name, data)})
            if attached.status_code >= 300:
                raise SystemExit(f'附件上传失败 {name}：{attached.status_code} {attached.text[:400]}')
        print('完成：https://gitee.com/' + REPO + '/releases/tag/' + TAG)


if __name__ == '__main__':
    main()
