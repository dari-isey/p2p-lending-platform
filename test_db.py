import asyncpg
import asyncio

async def main():
    conn = await asyncpg.connect(
        user='postgres',
        password='779058asb', 
        database='p2p_lending',
        host='127.0.0.1',
        port=5432
    )
    version = await conn.fetchval('SELECT version()')
    print("Версия PostgreSQL:", version)
    await conn.close()

asyncio.run(main())