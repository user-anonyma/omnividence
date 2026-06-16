/**
 * useAsync Hook
 * Manages async operations with loading, data, and error states
 */

import { useState, useEffect, useCallback } from 'react';

export const useAsync = (asyncFunction, immediate = true) => {
  const [state, setState] = useState({
    loading: immediate,
    data: null,
    error: null,
  });

  const execute = useCallback(async (...args) => {
    setState({ loading: true, data: null, error: null });
    try {
      const response = await asyncFunction(...args);
      setState({ loading: false, data: response, error: null });
      return response;
    } catch (error) {
      setState({
        loading: false,
        data: null,
        error: error,
      });
      throw error;
    }
  }, [asyncFunction]);

  useEffect(() => {
    if (!immediate) return;

    execute();
  }, [execute, immediate]);

  return {
    ...state,
    execute,
  };
};

export default useAsync;
