"""Shared labels; community and personal ratings have different meanings."""
def rating_text(work):
    source = next((s for s in work.get('sources', []) if s.get('rating') is not None), None)
    community = f"★ {source['rating']:.1f}" if source else '暂无评分'
    personal = f"我的 {work['rating']}" if work.get('rating') is not None else '未评分'
    return community + ' · ' + personal
