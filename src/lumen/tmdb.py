"""Host-owned configuration for the bundled TMDB metadata source."""
import re


ID = 'tmdb'
SETTINGS = 'tmdb'
API_ORIGIN = 'https://api.themoviedb.org:443'
IMAGE_ORIGIN = 'https://image.tmdb.org:443'
ATTRIBUTION = 'This product uses the TMDB API but is not endorsed or certified by TMDB.'


def settings(library):
    return library.setting(SETTINGS, {})


def save_settings(library, token, enabled):
    token = token.strip()
    if len(token) > 4096:
        raise ValueError('TMDB API 读取访问令牌过长。')
    if token and not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token):
        raise ValueError('请输入 TMDB 设置中的 API 读取访问令牌，而不是 v3 API Key。')
    if enabled and not token:
        raise ValueError('启用 TMDB 前，请填写 API 读取访问令牌。')
    library.set_setting(SETTINGS, {'token': token, 'enabled': bool(enabled)})
