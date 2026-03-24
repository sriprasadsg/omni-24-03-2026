
import { GoogleGenAI, FunctionDeclaration, Type } from "@google/genai";
import { Command } from '../components/AICommandBar';
import { AppView, SastFinding } from "../types";

const API_KEY = process.env.API_KEY;

if (!API_KEY) {
  console.warn("API_KEY environment variable not set. AI features may not work.");
}

const ai = new GoogleGenAI({ apiKey: API_KEY! });
const model = "gemini-flash-latest";

const navigateToView: FunctionDeclaration = {
    name: 'navigateToView',
    description: 'Navigates the user to a specific view or dashboard in the application.',
    parameters: {
        type: Type.OBJECT,
        properties: {
            view: {
                type: Type.STRING,
                description: 'The view to navigate to.',
                enum: [
                    'dashboard', 'reporting', 'agents', 'assetManagement', 
                    'patchManagement', 'cloudSecurity', 'security', 'compliance', 
                    'aiGovernance', 'finops', 'auditLog', 'settings', 
                    'tenantManagement', 'logExplorer', 'threatHunting', 'profile',
                    'automation', 'devsecops', 'developer_hub', 'incidentImpact',
                    'proactiveInsights', 'distributedTracing'
                ]
            }
        },
        required: ['view']
    }
};

const applyFilter: FunctionDeclaration = {
    name: 'applyFilter',
    description: 'Applies a filter to the current or a specified view to narrow down the displayed data.',
    parameters: {
        type: Type.OBJECT,
        properties: {
            view: {
                type: Type.STRING,
                description: 'The view where the filter should be applied.',
                enum: ['agents', 'assetManagement', 'security']
            },
            filterType: {
                type: Type.STRING,
                description: 'The type of filter to apply, e.g., "status" for agents or "vulnerability_severity" for assets.',
            },
            value: {
                type: Type.STRING,
                description: 'The value to filter by, e.g., "Error" for agent status or "Critical" for vulnerability severity.'
            }
        },
        required: ['view', 'filterType', 'value']
    }
};

export const getCommandFromQuery = async (query: string): Promise<Command[]> => {
    if (!API_KEY) {
        throw new Error("API Key is not configured.");
    }

    try {
        const response = await ai.models.generateContent({
            model: model,
            contents: `Based on the user query, call the appropriate function(s) to navigate or filter the application. User query: "${query}"`,
            config: {
                tools: [{ functionDeclarations: [navigateToView, applyFilter] }],
            }
        });

        if (response.functionCalls && response.functionCalls.length > 0) {
            return response.functionCalls.map(fc => ({
                name: fc.name,
                args: fc.args,
            }));
        }
        
        // Fallback or handle cases where no function is called
        // For example, you could try a text-only response for Q&A
        return [];
        
    } catch (error) {
        console.error("Error calling Gemini API:", error);
        throw new Error("Failed to communicate with the AI model.");
    }
};

export const generateSastFix = async (finding: SastFinding): Promise<{ fixedCode: string }> => {
    if (!API_KEY) {
        throw new Error("API Key is not configured.");
    }
    
    const prompt = `
        The following code snippet has a "${finding.type}" vulnerability.
        Vulnerable code:
        \`\`\`
        ${finding.codeSnippet}
        \`\`\`
        Provide a secure, corrected version of this code snippet. Only return the corrected code, with no additional explanation.
    `;

    try {
        const response = await ai.models.generateContent({
            model: model,
            contents: prompt,
        });

        const fixedCode = response.text.replace(/```/g, '').trim();

        return { fixedCode };

    } catch (error) {
        console.error("Error calling Gemini API for SAST fix:", error);
        throw new Error("Failed to generate SAST fix.");
    }
};