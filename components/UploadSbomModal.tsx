import React, { useState, useRef } from 'react';
import { XIcon, UploadCloudIcon, CogIcon } from './icons';

interface UploadSbomModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (file: File) => Promise<void>;
}

export const UploadSbomModal: React.FC<UploadSbomModalProps> = ({ isOpen, onClose, onUpload }) => {
  const [file, setFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsLoading(true);
    try {
      await onUpload(file);
      onClose();
    } catch (error) {
      // Error handled in parent
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-lg p-6 m-4" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center">
            <UploadCloudIcon className="mr-3 text-primary-500" />
            Upload SBOM
          </h2>
          <button onClick={onClose} className="p-1 rounded-full text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700">
            <XIcon size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Upload a Software Bill of Materials (SBOM) file (CycloneDX JSON) to identify software components and their vulnerabilities.
          </p>

          <div
            className="p-8 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-center cursor-pointer hover:border-primary-500 transition-colors"
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              className="hidden"
              accept=".json,.xml"
            />
            <UploadCloudIcon size={48} className="mx-auto text-gray-400 mb-2" />
            <p className="text-gray-500 dark:text-gray-400 text-sm font-medium">
              {file ? file.name : "Click to select or drag and drop SBOM file"}
            </p>
            <p className="text-xs text-gray-400 mt-1">Supported formats: CycloneDX JSON</p>
          </div>
        </div>

        <div className="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button type="button" onClick={onClose} disabled={isLoading} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white dark:bg-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md">
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={isLoading || !file}
            className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:bg-primary-400/50 disabled:cursor-wait flex items-center"
          >
            {isLoading ? (
              <><CogIcon size={16} className="animate-spin mr-2" /> Processing...</>
            ) : (
              'Upload & Process'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
