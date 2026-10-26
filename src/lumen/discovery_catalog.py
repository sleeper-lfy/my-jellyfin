"""Complete discovery queries shared by desktop and authenticated LAN clients."""
from datetime import datetime,timezone
import json
import math
from .catalog import SORTS,sort_items,validate_filters

DISCOVERY_SORTS={'discovered','site_added','community_rating',*SORTS}


def date_value(value):
    if not isinstance(value,str) or not value.strip():return None
    try:
        stamp=datetime.fromisoformat(value.strip().replace('Z','+00:00'))
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        return stamp.timestamp()
    except (ValueError,OverflowError,OSError):return None


def source_rating(work):
    # Match the first nonempty score displayed on current media cards.
    return next((float(source['rating']) for source in work.get('sources',[])
                 if type(source.get('rating')) in (int,float) and math.isfinite(source['rating'])),None)


def query_discovery(library,filters=None,*,source='',category='',tag_query=''):
    """Filter every matching record, then sort; callers paginate afterwards.

    Explicit ids are site-search hits, including safely matched local works
    without provider metadata. An explicitly empty hit list stays empty.
    """
    filters=dict(filters or {})
    field=filters.pop('sort','discovered');descending=filters.pop('descending',True)
    name=filters.pop('query','')
    if field not in DISCOVERY_SORTS or type(descending) is not bool:raise ValueError('无效发现排序')
    for value in (name,source,category,tag_query):
        if not isinstance(value,str) or len(value)>2000:raise ValueError('发现搜索条件过长或无效')
    validate_filters(filters)
    rows=library.query({**filters,'local':False,'sort':'added','query':''})
    name=name.strip().casefold();tag_query=tag_query.strip().casefold()
    selected=[]
    for work in rows:
        sources=work.get('sources',[]);metadata=work['metadata']
        if 'ids' not in filters and not sources:continue
        if source and not any(item['plugin']==source for item in sources):continue
        if category and category not in metadata.get('discovery_categories',[]):continue
        if name and not any(name in str(title).casefold() for title in [work['title'],*metadata.get('aliases',[])]):continue
        if tag_query and not any(tag_query in str(tag).casefold() for tag in metadata.get('tags',[])):continue
        selected.append(work)
    if field in SORTS:return sort_items(selected,field,descending)
    def value(work):
        if field=='community_rating':return source_rating(work)
        if field=='site_added':
            values=[date_value(item.get('site_added')) for item in work.get('sources',[]) if not source or item['plugin']==source]
            return max((item for item in values if item is not None),default=None)
        return date_value(work.get('discovered') or work.get('added'))
    known=[];missing=[]
    for work in selected:
        key=value(work)
        (missing if key is None else known).append(work if key is None else (key,work))
    known.sort(key=lambda item:item[1]['id'])
    known.sort(key=lambda item:item[0],reverse=descending)
    missing.sort(key=lambda item:item['id'])
    return [work for _,work in known]+missing


def discovery_facets(library,kinds=None):
    """The complete discovered catalog, independent of current query/results."""
    tags=set();categories=set();actors=set();years=set()
    for work in library.db.execute('SELECT kind,year,metadata FROM works WHERE EXISTS(SELECT 1 FROM sources WHERE work_id=works.id)'):
        if kinds is not None and work['kind'] not in kinds:continue
        data=json.loads(work['metadata']);tags.update(data.get('tags',[]));categories.update(data.get('discovery_categories',[]))
        for person in data.get('actors',[]):actors.update([person['name'],*person.get('aliases',[])])
        if work['year'] is not None:years.add(work['year'])
    return {'tags':sorted(tags,key=str.casefold),'categories':sorted(categories,key=str.casefold),
            'actors':sorted(actors,key=str.casefold),'years':sorted(years,reverse=True)}
