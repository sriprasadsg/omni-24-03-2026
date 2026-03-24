import React, { useEffect, useState } from 'react';
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { fetchBusinessKpis } from '../services/apiService';

interface BusinessKpiData {
  name: string;
  operationalEfficiency: number;
  securityIncidents: number;
  complianceScore: number;
}

export const BusinessKpiChart: React.FC = () => {
  const [data, setData] = useState<BusinessKpiData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        const result = await fetchBusinessKpis();
        // Handle mock structure: { trends: [...] }
        if (result && result.trends) {
          setData(result.trends);
        } else {
          setData([]);
        }
      } catch (error) {
        console.error('Failed to load business KPIs:', error);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  if (loading) {
    return <div className="h-80 flex items-center justify-center bg-white rounded-lg shadow-sm border border-gray-100">Loading chart data...</div>;
  }

  // Explicitly defining height to prevent Recharts crash (width -1)
  return (
    <div className="p-4 bg-white rounded-lg shadow-sm border border-gray-100 h-96 flex flex-col w-full">
      <h3 className="text-lg font-semibold text-gray-900 mb-4 flex-shrink-0">Business KPI Correlation</h3>
      <div className="flex-grow w-full min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data}
            margin={{
              top: 10,
              right: 20,
              bottom: 10,
              left: 0,
            }}
          >
            <CartesianGrid stroke="#f5f5f5" />
            <XAxis dataKey="name" scale="band" tick={{ fontSize: 12 }} />
            <YAxis yAxisId="left" orientation="left" stroke="#8884d8" tick={{ fontSize: 12 }} />
            <YAxis yAxisId="right" orientation="right" stroke="#82ca9d" tick={{ fontSize: 12 }} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar yAxisId="left" dataKey="operationalEfficiency" barSize={20} fill="#413ea0" name="Efficiency Score" />
            <Line yAxisId="right" type="monotone" dataKey="securityIncidents" stroke="#ff7300" name="Security Incidents" />
            <Line yAxisId="right" type="monotone" dataKey="complianceScore" stroke="#82ca9d" name="Compliance Score" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
