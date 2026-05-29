import asyncio
from src.tools.fetch import fetch_page

async def test():
    url = 'https://pro.arcgis.com/en/pro-app/latest/tool-reference/analysis/buffer.htm'
    r = await fetch_page(url)
    print(f'Title: {r.title}')
    print(f'Sections: {len(r.sections)}')
    print(f'Images: {len(r.images)}')
    print(f'Code blocks: {len(r.code_blocks)}')
    print(f'Error: {r.error}')
    
    assert r.title, "No title extracted"
    assert r.sections, "No sections extracted"
    assert r.images, "No images extracted"
    assert not r.error, f"Unexpected error: {r.error}"
    print('PASS - live fetch')

if __name__ == "__main__":
    asyncio.run(test())
