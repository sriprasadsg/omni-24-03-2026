// MongoDB User Creation Script
// Run this in mongosh to create admin and application users

// Step 1: Switch to admin database and create admin user
use admin

db.createUser({
    user: "omni_admin",
    pwd: "SecureAdmin#2025!MongoDB",  // CHANGE THIS PASSWORD!
    roles: ["root"]
})

print("✅ Admin user 'omni_admin' created successfully");

// Step 2: Switch to omni_platform database and create application user
use omni_platform

db.createUser({
    user: "omni_app",
    pwd: "SecureApp#2025!MongoDB",  // CHANGE THIS PASSWORD!
    roles: [
        { role: "readWrite", db: "omni_platform" }
    ]
})

print("✅ Application user 'omni_app' created successfully");

// Step 3: Test the users
print("\n📋 Testing user access...");

// Test app user
db.auth("omni_app", "SecureApp#2025!MongoDB");
print("✅ App user can authenticate");
print("Collections accessible: " + db.getCollectionNames());

// Exit
print("\n🎉 MongoDB users created successfully!");
print("⚠️  IMPORTANT: Change the passwords before production!");
print("⚠️  Store credentials securely - never commit to Git!");
