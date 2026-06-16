/**
 * ImageUploader Component
 * Handles drag-drop image upload with preview
 * Accessible and responsive
 */

import React, { useState, useRef, useCallback } from 'react';
import apiClient, { APIError } from '../../services/apiClient';
import { BATCH_LIMITS } from '../../config/api';
import './ImageUploader.css';

export const ImageUploader = ({ onUploadSuccess, onUploadError, onLoading }) => {
  const [preview, setPreview] = useState(null);
  const [fileName, setFileName] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);
  const dragCounterRef = useRef(0);

  const validateFile = useCallback((file) => {
    if (!file.type.startsWith('image/')) {
      throw new Error('Please upload a valid image file');
    }

    if (file.size > BATCH_LIMITS.MAX_FILE_SIZE) {
      throw new Error(
        `File size exceeds ${BATCH_LIMITS.MAX_FILE_SIZE / 1024 / 1024}MB limit`
      );
    }

    return true;
  }, []);

  const handleFileSelect = useCallback(
    async (file) => {
      setError(null);

      try {
        validateFile(file);
        setFileName(file.name);

        const reader = new FileReader();
        reader.onload = (e) => {
          setPreview(e.target.result);
        };
        reader.readAsDataURL(file);

        setIsUploading(true);
        onLoading?.(true);
        setUploadProgress(0);

        const response = await apiClient.uploadImage(file);

        if (response.success) {
          onUploadSuccess?.(response.data);
          setUploadProgress(100);
        } else {
          throw new Error(response.error || 'Upload failed');
        }
      } catch (err) {
        const errorMessage =
          err instanceof APIError ? err.message : err.message;
        setError(errorMessage);
        onUploadError?.(errorMessage);
        setPreview(null);
        setFileName('');
      } finally {
        setIsUploading(false);
        onLoading?.(false);
      }
    },
    [validateFile, onUploadSuccess, onUploadError, onLoading]
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

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleInputChange = (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  const handleClear = () => {
    setPreview(null);
    setFileName('');
    setError(null);
    setUploadProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="image-uploader">
      <div className="uploader-container">
        <div
          className="drop-zone"
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={handleClick}
          role="button"
          tabIndex="0"
          aria-label="Drag and drop image here or click to upload"
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
            onChange={handleInputChange}
            disabled={isUploading}
            aria-label="Select image file"
          />

          {!preview ? (
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
              <p className="drop-zone-text">
                {isUploading ? 'Uploading...' : 'Drag image here or click to upload'}
              </p>
              <p className="drop-zone-subtext">Supported formats: JPG, PNG, GIF, WebP</p>
            </div>
          ) : (
            <div className="preview-container">
              <img
                src={preview}
                alt="Uploaded preview"
                className="preview-image"
              />
              <p className="file-name">{fileName}</p>
              {uploadProgress > 0 && uploadProgress < 100 && (
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${uploadProgress}%` }}
                  ></div>
                </div>
              )}
              {uploadProgress === 100 && (
                <p className="success-text">Upload successful</p>
              )}
            </div>
          )}
        </div>

        {error && (
          <div className="error-message" role="alert">
            {error}
          </div>
        )}

        {preview && !isUploading && (
          <button
            className="clear-button"
            onClick={handleClear}
            aria-label="Clear uploaded image"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
};

export default ImageUploader;
