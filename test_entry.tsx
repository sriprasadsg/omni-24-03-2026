console.log("[TestEntry] Script is running!");
const root = document.getElementById('root');
if (root) {
    root.innerHTML = "<h1>Test Entry Successful</h1>";
    root.style.color = "green";
} else {
    console.error("[TestEntry] Root not found");
}
