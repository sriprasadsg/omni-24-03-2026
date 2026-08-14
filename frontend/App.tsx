// frontend/App.tsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import ItamRoutes from './routes/itamRoutes';

const App: React.FC = () => {
    return (
        <Router>
            <div className="min-h-screen bg-gray-100">
                <nav className="bg-white shadow p-4">
                    <ul className="flex space-x-4">
                        <li>
                            <Link to="/" className="text-blue-600 hover:underline">Home</Link>
                        </li>
                        <li>
                            <Link to="/itam" className="text-blue-600 hover:underline">ITAM</Link>
                        </li>
                        {/* Add other top-level navigation links here */}
                    </ul>
                </nav>
                <main className="container mx-auto mt-4">
                    <Routes>
                        <Route path="/" element={<div>Welcome to Omni Platform</div>} />
                        <Route path="/itam/*" element={<ItamRoutes />} />
                        {/* Add other top-level routes here */}
                    </Routes>
                </main>
            </div>
        </Router>
    );
};

export default App;