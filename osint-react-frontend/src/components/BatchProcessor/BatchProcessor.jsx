/**
 * BatchProcessor Component
 * Process multiple images for batch searching
 * Accessible and responsive
 */

import React, { useState, useRef, useCallback } from 'react';
import apiClient, { APIError } from '../../services/apiClient';
import { BATCH_LIMITS } from '../../config/api';
import './BatchProcessor.css';

export const BatchProcessor = ({ onBatchSuccess, onBatchError, onLoading }) => {
  const [files, setFiles] = useState([]);
  const [uploadProgress, setUploadProgress] = useState({});
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const fileInputRef = useRef(null);
  const dragCounterRef = useRef(0);

  const validateFiles = useCallback((filesToValidate) => {
    if (filesToValidate.length > BATCH_LIMITS.MAX_IMAGES) {
      throw new Error(
        `Maximum ${BATCH_LIMITS.MAX_IMAGES} images allowed per batch`
      );
    }

    let totalSize = 0;
    filesToValidate.forEach((file) => {
      if (!file.type.startsWith('image/')) {
        throw new Error(`Invalid file type: ${file.name}`);
      }

      if (file.size > BATCH_LIMITS.MAX_FILE_SIZE) {
        throw new Error(
          `File ${file.name} exceeds size limit`
        );
      }

      totalSize += file.size;
    });

    if (totalSize > BATCH_LIMITS.MAX_BATCH_SIZE) {
      throw new Error('Total batch size exceeds limit');
    }

    return true;
  }, []);

  const handleFileSelect = useCallback(
    (selectedFiles) => {
      setError(null);
      setSuccessMessage(null);

      try {
        const fileArray = Array.from(selectedFiles);
        validateFiles(fileArray);

        setFiles((prevFiles) => {
          const newFiles = [...prevFiles];
          fileArray.forEach((file) => {
            if (!newFiles.some((f) => f.name === file.name && f.size === file.size)) {
              newFiles.push(file);
              setUploadProgress((prev) => ({
                ...prev,
                [file.name]: 0,
              }));
            }
          });
          return newFiles;
        });
      } catch (err) {
        const errorMessage =
          err instanceof APIError ? err.message : err.message;
        setError(errorMessage);
        onBatchError?.(errorMessage);
      }
    },
    [validateFiles, onBatchError]
  );

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = 0;

    const droppedFiles = e.dataTransfer.files;
    handleFileSelect(droppedFiles);
  };

  const handleInputChange = (e) => {
    handleFileSelect(e.target.files);
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const removeFile = (fileName) => {
    setFiles((prevFiles) => prevFiles.filter((f) => f.name !== fileName));
    setUploadProgress((prev) => {
      const updated = { ...prev };
      delete updated[fileName];
      return updated;
    });
  };

  const clearAll = () => {
    setFiles([]);
    setUploadProgress({});
    setError(null);
    setSuccessMessage(null);
  };

  const processBatch = async () => {
    if (files.length === 0) {
      setError('No files selected');
      return;
    }

    setIsProcessing(true);
    onLoading?.(true);
    setError(null);

    try {
      const response = await apiClient.uploadBatch(files);

      if (response.success && response.data) {
        const processed = response.data.processed ?? response.data.total_images ?? files.length;
        setSuccessMessage(
          `Successfully processed ${processed} image(s)`
        );
        onBatchSuccess?.(response.data);
        clearAll();
      } else {
        throw new Error(response.error || 'Batch upload failed');
      }
    } catch (err) {
      const errorMessage =
        err instanceof APIError ? err.message : err.message;
      setError(errorMessage);
      onBatchError?.(errorMessage);
    } finally {
      setIsProcessing(false);
      onLoading?.(false);
    }
  };

  const totalSize = files.reduce((sum, file) => sum + file.size, 0);
  const totalSizeMB = (totalSize / 1024 / 1024).toFixed(2);

  return (
    <div className="batch-processor">
      <div className="processor-container">
        <h2 className="processor-title">Batch Image Upload</h2>

        <div
          className="batch-drop-zone"
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={handleClick}
          role="button"
          tabIndex="0"
          aria-label="Drag and drop multiple images here or click to upload batch"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              handleClick();
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handleInputChange}
            disabled={isProcessing}
            aria-label="Select multiple image files"
          />

          {files.length === 0 ? (
            <div className="drop-zone-content">
              <svg
                className="drop-zone-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              <p className="drop-zone-text">Drag multiple images here or click to upload</p>
              <p className="drop-zone-subtext">
                Max {BATCH_LIMITS.MAX_IMAGES} images, {BATCH_LIMITS.MAX_FILE_SIZE / 1024 / 1024}MB each
              </p>
            </div>
          ) : (
            <div className="files-list-container">
              <p className="files-count">
                {files.length} file{files.length !== 1 ? 's' : ''} selected ({totalSizeMB}MB)
              </p>
            </div>
          )}
        </div>

        {error && (
          <div className="error-message" role="alert">
            {error}
          </div>
        )}

        {successMessage && (
          <div className="success-message" role="status">
            {successMessage}
          </div>
        )}

        {files.length > 0 && (
          <div className="files-section">
            <h3>Files to Upload</h3>
            <div className="files-list">
              {files.map((file) => (
                <div key={file.name} className="file-item">
                  <div className="file-info">
                    <p className="file-name">{file.name}</p>
                    <p className="file-size">
                      {(file.size / 1024 / 1024).toFixed(2)}MB
                    </p>
                  </div>
                  <button
                    className="remove-file-button"
                    onClick={() => removeFile(file.name)}
                    disabled={isProcessing}
                    aria-label={`Remove ${file.name}`}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>

            <div className="batch-actions">
              <button
                className="process-button"
                onClick={processBatch}
                disabled={isProcessing || files.length === 0}
                aria-label="Start batch upload"
              >
                {isProcessing ? 'Processing...' : `Upload ${files.length} Image${files.length !== 1 ? 's' : ''}`}
              </button>
              <button
                className="clear-all-button"
                onClick={clearAll}
                disabled={isProcessing}
                aria-label="Clear all files"
              >
                Clear All
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default BatchProcessor;
