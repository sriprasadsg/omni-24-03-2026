import asyncio, json; from backend.database import get_database; async def main():
 db=get_database()
 agents=await db.agents.find().to_list(10)
 for a in agents: print(a.get('hostname'), a.get('status'), a.get('lastSeen'))
asyncio.run(main())
