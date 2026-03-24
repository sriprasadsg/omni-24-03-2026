"""
Check specific asset fields for final verification
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_asset_summary():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    
    asset = await db.assets.find_one({"hostname": "EILT0197"})
    
    if asset:
        print("\n--- FINAL ASSET SUMMARY ---")
        print(f"Hostname:    {asset.get('hostname')}")
        print(f"CPU Model:   {asset.get('cpuModel')}")
        print(f"OS Name:     {asset.get('osName')}")
        print(f"OS Edition:  {asset.get('osEdition')}")
        print(f"OS Version:  {asset.get('osDisplayVersion')} (Display) / {asset.get('osVersion')} (Internal)")
        print(f"OS Build:    {asset.get('osBuild')}")
        print(f"Installed:   {asset.get('osInstalledOn')}")
        print(f"Experience:  {asset.get('osExperience')}")
        print(f"Kernel:      {asset.get('kernel')}")
        print(f"Serial:      {asset.get('serialNumber')}")
        print(f"IP Address:  {asset.get('ipAddress')}")
        print(f"MAC Address: {asset.get('macAddress')}")
        print(f"RAM Total:   {asset.get('ram')}")
        
        metrics = asset.get('currentMetrics', {})
        print("\n--- LIVE METRICS ---")
        print(f"CPU Usage:    {metrics.get('cpuUsage')}%")
        print(f"Memory Usage: {metrics.get('memoryUsage')}%")
        print(f"Disk Usage:   {metrics.get('diskUsage')}%")
    else:
        print("\n❌ Asset EILT0197 not found in database")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_asset_summary())
