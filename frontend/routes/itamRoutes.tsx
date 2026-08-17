// frontend/routes/itamRoutes.tsx
import React from 'react';
import { Route, Routes } from 'react-router-dom';
import PurchaseOrderList from '../components/itam/procurement/PurchaseOrderList';
import PurchaseOrderDetail from '../components/itam/procurement/PurchaseOrderDetail';

// Placeholder for ITAM Dashboard or a main ITAM entry point component
const ItamDashboard: React.FC = () => {
    return (
        <div className="p-4">
            <h1 className="text-3xl font-bold mb-6">ITAM Dashboard</h1>
            <nav className="mb-4">
                <ul className="flex space-x-4">
                    <li><Link to="/itam/purchase-orders" className="text-blue-600 hover:underline">Purchase Orders</Link></li>
                    {/* Add other ITAM navigation links here */}
                </ul>
            </nav>
            {/* Render a default view or sub-routes */}
            <Routes>
                <Route path="purchase-orders" element={<PurchaseOrderList />} />
                <Route path="purchase-orders/:id" element={<PurchaseOrderDetail />} />
                {/* Add routes for creating/editing purchase orders if separate components are made */}
                {/* <Route path="purchase-orders/new" element={<PurchaseOrderForm />} /> */}
                {/* <Route path="purchase-orders/:id/edit" element={<PurchaseOrderForm />} /> */}
            </Routes>
        </div>
    );
};

// Main ITAM router component
const ItamRoutes: React.FC = () => {
    return (
        <Routes>
            <Route path="/" element={<ItamDashboard />} >
                 <Route path="purchase-orders" element={<PurchaseOrderList />} />
                 <Route path="purchase-orders/:id" element={<PurchaseOrderDetail />} />
            </Route>
        </Routes>
    );
};

export default ItamRoutes;