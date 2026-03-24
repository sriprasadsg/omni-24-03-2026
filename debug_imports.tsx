console.log("[DebugImports] Starting import verification...");

const verifyImport = async (name: string, path: string) => {
    try {
        console.log(`[DebugImports] Importing ${name}...`);
        await import(path);
        console.log(`[DebugImports] Success: ${name}`);
    } catch (e) {
        console.error(`[DebugImports] FAILED: ${name}`, e);
        document.body.innerHTML += `<div style="color:red">Failed: ${name} <br/> ${e}</div>`;
    }
};

(async () => {
    // core
    await verifyImport('Sidebar', './components/Sidebar');
    await verifyImport('Header', './components/Header');
    await verifyImport('ApiService', './services/apiService');

    // New Dashboards
    await verifyImport('DataWarehouse', './components/DataWarehouseDashboard');
    await verifyImport('Streaming', './components/StreamingDashboard');
    await verifyImport('DataGovernance', './components/DataGovernanceDashboard');
    await verifyImport('MLOps', './components/MLOpsDashboard');
    await verifyImport('AutoML', './components/AutoMLDashboard');
    await verifyImport('XAI', './components/XAIDashboard');
    await verifyImport('ABTesting', './components/ABTestingDashboard');

    console.log("[DebugImports] All checks complete.");
})();
