import asyncio
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

async def test():
    dl = SQLAlchemyDataLayer(conninfo='sqlite+aiosqlite:///chainlit.db')
    u = await dl.get_user('abc')
    print('User=', u.__dict__ if u else 'None')

if __name__ == '__main__':
    asyncio.run(test())
