"""Validated naming rules used by preview and automatic organization alike."""
import re
from pathlib import Path
from string import Formatter

FIELDS = {'code', 'title', 'year', 'year_suffix', 'stem', 'part', 'season', 'episode', 'version'}
DEFAULT_RULE = {'folder': '', 'filename': ''}


def rule_key(kind='movie', path=None):
    return 'naming:directory:' + str(Path(path).resolve()) if path else 'naming:kind:' + kind


def validate_rule(rule):
    if not isinstance(rule, dict) or not rule.keys() <= {'folder', 'filename'}:
        raise ValueError('无效命名规则')
    clean = {field: str(rule.get(field, '')).strip() for field in ('folder', 'filename')}
    for field, template in clean.items():
        if len(template) > 300:
            raise ValueError('命名模板不能超过 300 个字符')
        if not template:
            continue
        if '\\' in template or template.startswith('/') or re.search(r'[<>:"|?*\x00-\x1f]', template):
            raise ValueError('模板含非法路径字符；子目录请使用 / 分隔')
        if field == 'filename' and '/' in template:
            raise ValueError('文件名模板不能包含目录分隔符')
        if any(part.strip(' .') == '' or part in {'.', '..'} for part in template.split('/')):
            raise ValueError('模板不能包含空目录、. 或 ..')
        try:
            pieces = list(Formatter().parse(template))
        except ValueError as error:
            raise ValueError('模板括号不完整') from error
        for literal, name, spec, conversion in pieces:
            if name is not None and (name not in FIELDS or spec or conversion):
                raise ValueError('只支持这些字段：' + ', '.join(sorted(FIELDS)))
    return clean


def load_rule(library, kind, destination):
    specific = library.setting(rule_key(kind, destination), None)
    return validate_rule(specific if specific is not None else library.setting(rule_key(kind), DEFAULT_RULE))


def save_rule(library, kind, rule, path=None):
    if kind not in {'movie', 'series', 'vr', 'other', 'fans'}:
        raise ValueError('无效媒体分类')
    clean = validate_rule(rule)
    library.set_setting(rule_key(kind, path), clean)
    return clean


def part_label(stem):
    match = re.search(r'(?i)(?:^|[\s._-])(?:CD|DISC|DISK|PART)[\s._-]*(\d{1,3})(?=$|[\s._-])', stem)
    return 'CD' + str(int(match[1])) if match else ''


def context(work, file, ordinal):
    from .ingestion import work_codes, codes
    from .files import safe_name
    identifiers = work_codes(work)
    if not identifiers:
        for value in work['metadata'].get('external_ids', {}).values():
            identifiers.update(codes(value))
    source = Path(file['path'])
    return {'code': next(iter(identifiers)) if len(identifiers) == 1 else '',
            'title': safe_name(work['title']), 'year': str(work['year'] or ''),
            'year_suffix': f" ({work['year']})" if work['year'] else '',
            'stem': safe_name(source.stem), 'part': part_label(source.stem),
            'season': f"{file['season']:02}" if file.get('season') is not None else '',
            'episode': f"{file['episode']:02}" if file.get('episode') is not None else '',
            'version': f'V{ordinal:02}'}


def render(template, values):
    from .files import safe_name
    for _, field, _, _ in Formatter().parse(template):
        if field in {'code', 'year', 'season', 'episode'} and not values[field]:
            raise ValueError('当前影片缺少模板所需字段：' + field)
    rendered = template.format_map(values)
    result = []
    for segment in rendered.split('/'):
        if not segment.strip(' .') or segment in {'.', '..'}:
            raise ValueError('模板产生空目录或非法路径')
        result.append(safe_name(segment))
    return Path(*result)


def destinations(work, root, rule):
    """Return one folder/name per file, adding stable-plan part/version suffixes."""
    from .files import safe_name
    result = []
    for ordinal, file in enumerate(sorted(work['files'], key=lambda item: item['id']), 1):
        source = Path(file['path']); values = context(work, file, ordinal)
        folder = root / (render(rule['folder'], values) if rule['folder'] else
                         safe_name(work['title'] + (f" ({work['year']})" if work['year'] else '')))
        if work['kind'] == 'series' and '{season}' not in rule['folder']:
            folder /= f"Season {file['season']:02}" if file['season'] is not None else '未分季'
        if work['kind'] == 'other' and not rule['folder']:
            folder = root / Path(file['root']).name / source.relative_to(file['root']).parent
        stem = str(render(rule['filename'], values)) if rule['filename'] else source.stem
        if rule['filename']:
            # Parts and episodes must remain distinguishable even in a simple {code} template.
            suffix = values['part']
            if work['kind'] == 'series' and values['season'] and values['episode']:
                suffix = 'S' + values['season'] + 'E' + values['episode']
            if suffix and not re.search(r'(?i)(?:^|[ ._-])' + re.escape(suffix) + r'(?:$|[ ._-])', stem):
                stem = safe_name(stem[:130] + '-' + suffix)
        show_folder=folder.parent if work['kind']=='series' and '{season}' not in rule['folder'] else folder
        if work['kind']=='series' and '{season}' in rule['folder']:
            parts=rule['folder'].split('/')
            season_index=next(index for index,part in enumerate(parts) if '{season}' in part)
            show_folder=root / render('/'.join(parts[:season_index]),values) if season_index else root
        result.append({'file': file, 'folder': folder, 'stem': stem, 'ordinal': ordinal, 'show_folder':show_folder})
    if rule['filename']:
        groups = {}
        for item in result:
            groups.setdefault(str(item['folder'] / item['stem']).casefold(), []).append(item)
        for items in groups.values():
            if len(items) > 1:
                for item in items:
                    item['stem'] = safe_name(item['stem'][:130] + f"-V{item['ordinal']:02}")
    return result


def nfo_image_references(path):
    """Read bounded XML image references without resolving remote or escaping paths."""
    import xml.etree.ElementTree as ET
    from .nfo import MAX_NFO
    try:
        with path.open('rb') as stream: data = stream.read(MAX_NFO + 1)
        if len(data)>MAX_NFO or re.search(br'<!\s*(DOCTYPE|ENTITY)',data.replace(b'\x00',b''),re.I): return []
        tree=ET.fromstring(data)
    except (OSError,ET.ParseError): return []
    references=[]
    for item in tree.iter():
        if item.tag not in {'thumb','poster','fanart','image'} or not item.text: continue
        value=item.text.strip().replace('\\','/')
        relative=Path(value)
        if ':' in value or relative.is_absolute() or '..' in relative.parts:continue
        source=path.parent/relative
        if (source.suffix.lower() in {'.jpg','.jpeg','.png','.webp'} and source.is_file()
                and not source.is_symlink() and source.resolve().is_relative_to(path.parent.resolve())):
            references.append((source,relative))
    return list(dict.fromkeys(references))


def companion_copies(work, items, pairs, root):
    """NFO artwork keeps relative names; shared artwork/show NFO originals stay put."""
    from .core import VIDEO_EXTENSIONS
    nfos=[(Path(pair['source']),Path(pair['target'])) for pair in pairs if Path(pair['source']).suffix.lower()=='.nfo']
    copies=[]
    for item in items:
        file=item['file'];source=Path(file['path']);folder=item['folder']
        if work['kind']=='series':
            current=source.parent;bound=Path(file['root']).resolve()
            while current.resolve().is_relative_to(bound):
                show=current/'tvshow.nfo'
                if show.is_file() and not show.is_symlink():
                    # A custom season hierarchy still keeps the show NFO above that season.
                    target_folder=item.get('show_folder',folder.parent)
                    nfos.append((show,target_folder/'tvshow.nfo'));copies.append((show,target_folder/'tvshow.nfo'));break
                if current==current.parent:break
                current=current.parent
        elif work['kind'] in {'movie','vr'}:
            siblings=[p for p in source.parent.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
            if len(siblings)==1:
                generic=source.parent/'movie.nfo'
                if generic.is_file() and not generic.is_symlink():
                    nfos.append((generic,folder/'movie.nfo'));copies.append((generic,folder/'movie.nfo'))
        # Conventional artwork is copied only when this work owns every video in its folder.
        owned={Path(entry['path']).resolve() for entry in work['files']}
        if all(path.resolve() in owned for path in source.parent.iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS and path.is_file()):
            for name in ('poster.jpg','poster.png','folder.jpg','fanart.jpg','fanart.png','backdrop.jpg','backdrop.png'):
                image=source.parent/name
                if image.is_file() and not image.is_symlink():copies.append((image,folder/name))
    for nfo,target in nfos:
        for source,relative in nfo_image_references(nfo):copies.append((source,target.parent/relative))
    return list(dict.fromkeys(copies))
