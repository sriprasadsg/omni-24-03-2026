// Remove duplicate assets - keep most recent based on lastSeen
db = db.getSiblingDB('omni_agent_db');

// Authenticate
db.auth('omni_app', 'SecureApp#2025!MongoDB');

print("🔍 Finding duplicate assets...");

// Find duplicates
const duplicates = db.assets.aggregate([
    {
        $group: {
            _id: "$id",
            count: { $sum: 1 },
            entries: { $push: "$$ROOT" }
        }
    },
    {
        $match: { count: { $gt: 1 } }
    }
]).toArray();

if (duplicates.length === 0) {
    print("✅ No duplicate assets found!");
} else {
    print(`⚠️  Found ${duplicates.length} asset ID(s) with duplicates`);

    let totalRemoved = 0;

    duplicates.forEach(dupGroup => {
        const assetId = dupGroup._id;
        const entries = dupGroup.entries;

        print(`\n  Asset ID: ${assetId} (${dupGroup.count} entries)`);

        // Sort by lastSeen (most recent first)
        entries.sort((a, b) => {
            const aDate = a.lastSeen || "";
            const bDate = b.lastSeen || "";
            return bDate.localeCompare(aDate);
        });

        // Keep first, delete rest
        const keep = entries[0];
        const toDelete = entries.slice(1);

        print(`  Keeping: ${keep._id} (lastSeen: ${keep.lastSeen || 'N/A'})`);

        toDelete.forEach(entry => {
            print(`  Deleting: ${entry._id} (lastSeen: ${entry.lastSeen || 'N/A'})`);
            const result = db.assets.deleteOne({ _id: entry._id });
            if (result.deletedCount > 0) {
                totalRemoved++;
            }
        });
    });

    print(`\n✅ Cleanup complete! Removed ${totalRemoved} duplicate asset(s).`);
}

// Verify
const totalAssets = db.assets.countDocuments({});
const uniqueIds = db.assets.distinct("id").length;

print("\n📊 Final Stats:");
print(`  Total assets: ${totalAssets}`);
print(`  Unique IDs: ${uniqueIds}`);

if (totalAssets === uniqueIds) {
    print("  ✅ All assets have unique IDs!");
} else {
    print(`  ⚠️  Warning: Still have ${totalAssets - uniqueIds} duplicates`);
}
