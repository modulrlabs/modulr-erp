import React, { useState } from 'react';
import axios from 'axios';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, FileSpreadsheet, Upload, X } from 'lucide-react';
import { uploadProductsCsv } from '../../api/inventory';
import type { CsvImportResponse } from '../../types/erp';

interface CsvImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export const CsvImportModal: React.FC<CsvImportModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [result, setResult] = useState<CsvImportResponse | null>(null);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadProductsCsv(file),
    onSuccess: (data) => {
      setResult(data);
      setUploadError(null);
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['categories'] });
      onSuccess?.();
    },
    onError: (err: unknown) => {
      if (axios.isAxiosError(err)) {
        const data = err.response?.data as { detail?: string; file?: string[] } | undefined;
        setUploadError(data?.detail || data?.file?.[0] || 'Failed to upload CSV file.');
      } else {
        setUploadError('An unexpected error occurred during CSV import.');
      }
    },
  });

  if (!isOpen) return null;

  const handleClose = () => {
    setSelectedFile(null);
    setUploadError(null);
    setResult(null);
    onClose();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setUploadError(null);
    if (!selectedFile) {
      setUploadError('Please select a .csv file to upload.');
      return;
    }
    uploadMutation.mutate(selectedFile);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-indigo-600" />
            <h2 className="text-lg font-bold text-slate-900">Bulk CSV Product Import</h2>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 space-y-1">
          <p className="font-bold text-slate-800">Expected CSV Columns:</p>
          <p className="font-mono text-[11px] text-indigo-700 break-all">
            name, barcode, category, cost_price, selling_price, stock_quantity, reorder_level
          </p>
        </div>

        {uploadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{uploadError}</span>
          </div>
        )}

        {result && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-4 space-y-2 text-xs">
            <div className="flex items-center gap-2 font-bold text-emerald-800">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{result.message}</span>
            </div>
            <div className="flex gap-4 font-semibold text-slate-700">
              <span>Created: {result.created}</span>
              <span>Updated: {result.updated}</span>
              <span>Errors: {result.errors.length}</span>
            </div>

            {result.errors.length > 0 && (
              <div className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-amber-200 bg-white p-2.5 text-[11px] text-red-700 space-y-1">
                {result.errors.map((errMsg, idx) => (
                  <p key={idx}>{errMsg}</p>
                ))}
              </div>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Select CSV File *
            </label>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => {
                setSelectedFile(e.target.files?.[0] ?? null);
                setResult(null);
                setUploadError(null);
              }}
              className="block w-full min-h-[44px] rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-xs file:font-bold file:text-indigo-700 hover:file:bg-indigo-100"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="min-h-[44px] rounded-xl border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
            >
              Close
            </button>
            <button
              type="submit"
              disabled={uploadMutation.isPending || !selectedFile}
              className="min-h-[44px] inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
            >
              <Upload className="h-4 w-4" />
              <span>{uploadMutation.isPending ? 'Uploading...' : 'Upload & Import'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
