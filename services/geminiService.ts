import { Command } from '../components/AICommandBar';
import { AppView, SastFinding } from "../types";

// Note: LLM calls are now proxied through the backend /api/ai-proxy

export const getCommandFromQuery = async (query: string): Promise<Command[]> => {
    try {
        const token = localStorage.getItem('token');
        const response = await fetch('/api/ai-proxy/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                provider: 'ollama', // Proxy will respect LLM_PROVIDER if set
                model: 'llama3.2:3b',
                messages: [
                    {
                        role: 'system',
                        content: 'You are an AI command parser. Based on the user query, call the appropriate function(s) to navigate or filter the application. Respond with navigation tags like [NAVIGATE:view_name].'
                    },
                    {
                        role: 'user',
                        content: query
                    }
                ],
                temperature: 0.1
            })
        });

        if (!response.ok) {
            throw new Error(`Proxy error: ${response.statusText}`);
        }

        const data = await response.json();
        const content = data.choices ? data.choices[0].message.content : (data.response || "");

        const commands: Command[] = [];
        const navMatch = content.match(/\[NAVIGATE:(\w+)\]/);
        if (navMatch) {
            commands.push({
                name: 'navigateToView',
                args: { view: navMatch[1] }
            });
        }
        
        return commands;

    } catch (error) {
        console.error("Error calling AI Proxy:", error);
        throw new Error("Failed to communicate with the AI model.");
    }
};

export const generateSastFix = async (finding: SastFinding): Promise<{ fixedCode: string }> => {
    try {
        const token = localStorage.getItem('token');
        const prompt = `
            The following code snippet has a "${finding.type}" vulnerability.
            Vulnerable code:
            \`\`\`
            ${finding.codeSnippet}
            \`\`\`
            Provide a secure, corrected version of this code snippet. Only return the corrected code, with no additional explanation.
        `;

        const response = await fetch('/api/ai-proxy/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                provider: 'ollama',
                model: 'llama3.2:3b',
                messages: [{ role: 'user', content: prompt }],
                temperature: 0.1
            })
        });

        if (!response.ok) {
            throw new Error(`Proxy error: ${response.statusText}`);
        }

        const data = await response.json();
        const content = data.choices ? data.choices[0].message.content : (data.response || "");
        const fixedCode = content.replace(/```/g, '').replace(/```\w*/, '').trim();

        return { fixedCode };

    } catch (error) {
        console.error("Error calling AI Proxy for SAST fix:", error);
        throw new Error("Failed to generate SAST fix.");
    }
};