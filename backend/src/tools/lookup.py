from pydantic import BaseModel


class LookupResult(BaseModel):
    url: str
    title: str


URL_MAP: dict[str, dict[str, str]] = {
    "buffer": {
        "url": "https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm",
        "title": "Buffer (Analysis)",
    },
    "clip": {
        "url": "https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/clip.htm",
        "title": "Clip (Analysis)",
    },
    "intersect": {
        "url": "https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/intersect.htm",
        "title": "Intersect (Analysis)",
    },
    "merge": {
        "url": "https://pro.arcgis.com/en/pro-app/latest/tool-reference/data-management/merge.htm",
        "title": "Merge (Data Management)",
    },
    "geodatabase": {
        "url": "https://pro.arcgis.com/en/pro-app/latest/help/data/geodatabases/overview/what-is-a-geodatabase-.htm",
        "title": "What is a geodatabase?",
    },
    "arcpy": {
        "url": "https://pro.arcgis.com/en/pro-app/latest/arcpy/get-started/what-is-arcpy-.htm",
        "title": "What is ArcPy?",
    },
}


async def lookup_url(query: str) -> LookupResult | None:
    cleaned = query.lower().strip()

    if cleaned in URL_MAP:
        entry = URL_MAP[cleaned]
        return LookupResult(url=entry["url"], title=entry["title"])

    for key, entry in URL_MAP.items():
        if cleaned in key or key in cleaned:
            return LookupResult(url=entry["url"], title=entry["title"])

    return None
