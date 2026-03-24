"""
Remove duplicate service pricing entries from the database.
Keeps the first occurrence of each service and removes duplicates.
"""
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def remove_duplicate_service_pricing():
    """Remove duplicate service pricing entries"""
    print("=" * 70)
    print("REMOVING DUPLICATE SERVICE PRICING ENTRIES")
    print("=" * 70)
    
    try:
        await connect_to_mongo()
        db = get_database()
        
        if not db:
            print("❌ Failed to connect to database")
            return
        
        print("✓ Connected to database\n")
        
        # Get all service pricing entries
        all_services = await db.service_pricing.find({}).to_list(length=1000)
        
        if not all_services:
            print("❌ No service pricing entries found")
            await close_mongo_connection()
            return
        
        print(f"Found {len(all_services)} total service pricing entries\n")
        print("-" * 70)
        
        # Track unique service IDs and duplicates
        seen_ids = set()
        duplicates_to_remove = []
        kept_services = []
        
        for service in all_services:
            service_id = service.get('id')
            service_name = service.get('name', 'Unknown')
            
            if service_id in seen_ids:
                # This is a duplicate
                duplicates_to_remove.append(service)
                print(f"❌ DUPLICATE: {service_name} (ID: {service_id})")
                print(f"   MongoDB _id: {service['_id']}")
            else:
                # First occurrence - keep it
                seen_ids.add(service_id)
                kept_services.append(service)
                print(f"✅ KEEP: {service_name} (ID: {service_id})")
        
        print("-" * 70)
        print(f"\nSummary:")
        print(f"  Total entries: {len(all_services)}")
        print(f"  Unique services to keep: {len(kept_services)}")
        print(f"  Duplicates to remove: {len(duplicates_to_remove)}")
        print("=" * 70)
        
        if duplicates_to_remove:
            print(f"\n⚠️  Found {len(duplicates_to_remove)} duplicate(s) to remove:")
            for dup in duplicates_to_remove:
                print(f"   - {dup.get('name')} (MongoDB _id: {dup['_id']})")
            
            # Remove duplicates
            print("\n" + "=" * 70)
            print("REMOVING DUPLICATES...")
            print("=" * 70)
            
            removed_count = 0
            for dup in duplicates_to_remove:
                result = await db.service_pricing.delete_one({'_id': dup['_id']})
                if result.deleted_count > 0:
                    removed_count += 1
                    print(f"✅ Removed: {dup.get('name')} (ID: {dup.get('id')})")
                else:
                    print(f"❌ Failed to remove: {dup.get('name')}")
            
            print("\n" + "=" * 70)
            print("REMOVAL COMPLETE")
            print("=" * 70)
            print(f"Successfully removed {removed_count} duplicate(s)")
            print("=" * 70)
            
            # Verify final state
            final_count = await db.service_pricing.count_documents({})
            print(f"\n✅ Final service pricing count: {final_count}")
            
        else:
            print("\n✅ No duplicates found! Database is clean.")
        
        await close_mongo_connection()
        print("\nClosed MongoDB connection")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(remove_duplicate_service_pricing())

