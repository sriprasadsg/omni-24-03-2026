import React, { useState } from 'react';
import { GavelIcon, ShieldCheckIcon, UsersIcon, ActivityIcon, ChevronDownIcon } from './icons';

interface PolicySectionProps {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  isOpen: boolean;
  onToggle: () => void;
}

const PolicySection: React.FC<PolicySectionProps> = ({ icon, title, children, isOpen, onToggle }) => (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
        <header className="p-4 border-b border-gray-200 dark:border-gray-700 cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/50" onClick={onToggle}>
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-semibold flex items-center text-gray-800 dark:text-white">
                    {icon}
                    <span className="ml-3">{title}</span>
                </h3>
                <ChevronDownIcon size={20} className={`text-gray-500 dark:text-gray-400 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} />
            </div>
        </header>
        {isOpen && (
            <div className="p-6 prose prose-sm dark:prose-invert max-w-none">
                {children}
            </div>
        )}
    </div>
);

export const AIGovernancePolicy: React.FC = () => {
  const [openSection, setOpenSection] = useState<string | null>('purpose');

  const toggleSection = (sectionId: string) => {
    setOpenSection(openSection === sectionId ? null : sectionId);
  };

  return (
    <div className="space-y-6">
        <PolicySection 
            icon={<GavelIcon size={22} className="text-primary-500" />} 
            title="AI Governance Policy (ISO 42001:2023)"
            isOpen={openSection === 'purpose'}
            onToggle={() => toggleSection('purpose')}
        >
            <h4>1. Purpose</h4>
            <p>This policy establishes the framework for the responsible design, development, deployment, and management of all Artificial Intelligence (AI) systems within Omni-Agent AI Corp. Its purpose is to ensure that our AI activities align with our ethical principles, meet legal and regulatory requirements, and build trust with our stakeholders, in accordance with ISO 42001:2023.</p>
            
            <h4>2. Scope</h4>
            <p>This policy applies to all employees, contractors, and third parties involved in the entire lifecycle of AI systems, from conception and data collection to decommissioning. It covers all AI models, platforms, and related data used or developed by or on behalf of the organization.</p>
        </PolicySection>

        <PolicySection 
            icon={<ShieldCheckIcon size={22} className="text-primary-500" />} 
            title="Core Principles"
            isOpen={openSection === 'principles'}
            onToggle={() => toggleSection('principles')}
        >
            <ul>
                <li><strong>Fairness and Non-Discrimination:</strong> We are committed to developing AI systems that are fair and equitable. We will proactively identify and mitigate harmful biases in our data and models to prevent discriminatory outcomes.</li>
                <li><strong>Transparency and Explainability:</strong> We will be transparent about our use of AI. Our AI systems will be designed to be explainable, allowing stakeholders to understand their operations and the basis for their decisions.</li>
                <li><strong>Accountability and Human Oversight:</strong> We are accountable for the impact of our AI systems. All AI systems will have meaningful human oversight to ensure they operate as intended and that there are clear lines of responsibility for their outcomes.</li>
                <li><strong>Privacy and Security:</strong> AI systems will be designed with privacy and security at their core, adhering to data minimization principles and employing robust security controls to protect data from unauthorized access or use.</li>
            </ul>
        </PolicySection>

        <PolicySection 
            icon={<UsersIcon size={22} className="text-primary-500" />} 
            title="Roles and Responsibilities"
            isOpen={openSection === 'roles'}
            onToggle={() => toggleSection('roles')}
        >
            <dl>
                <dt>AI Ethics Committee (AEC)</dt>
                <dd>An interdisciplinary body responsible for overseeing AI governance, reviewing high-impact AI systems, and providing guidance on ethical considerations. The AEC must approve all high-risk AI systems before deployment.</dd>

                <dt>Compliance Officer</dt>
                <dd>Ensures that all AI systems and related processes comply with this policy, as well as relevant laws and regulations like GDPR and ISO 42001.</dd>
                
                <dt>Data Scientists & ML Engineers</dt>
                <dd>Responsible for designing, building, and testing AI systems in accordance with this policy, including conducting bias assessments and documenting model behavior.</dd>
                
                <dt>System Owners</dt>
                <dd>Accountable for the ongoing performance, safety, and impact of their assigned AI system throughout its operational lifecycle.</dd>
            </dl>
        </PolicySection>
        
        <PolicySection 
            icon={<ActivityIcon size={22} className="text-primary-500" />} 
            title="AI System Lifecycle Management"
            isOpen={openSection === 'lifecycle'}
            onToggle={() => toggleSection('lifecycle')}
        >
            <ol>
                <li><strong>Design & Development:</strong> An AI Impact Assessment must be completed to identify potential risks and societal impacts before development begins.</li>
                <li><strong>Data Governance:</strong> Data used for training and operating AI systems must be relevant, accurate, and handled with appropriate privacy and security controls. Data provenance must be documented.</li>
                <li><strong>Testing & Validation:</strong> All AI systems must undergo rigorous testing for performance, reliability, fairness, and security before deployment. Validation results must be documented in a model card.</li>
                <li><strong>Deployment & Monitoring:</strong> Deployed systems must be continuously monitored for performance, model drift, and unintended outcomes. An operational log must be maintained.</li>
                <li><strong>Incident Response:</strong> A clear process must be in place for responding to and remediating incidents caused by an AI system, including stakeholder notification where required.</li>
                <li><strong>Decommissioning:</strong> A formal process must be followed to retire AI systems, including data deletion and stakeholder communication.</li>
            </ol>
        </PolicySection>
    </div>
  );
};
