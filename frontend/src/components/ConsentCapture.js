import React, { useState } from "react";
import { FileCheck, AlertCircle, CheckCircle, User, Calendar, Shield } from "lucide-react";

const ConsentCapture = ({ patient, onConsentCaptured, onCancel }) => {
  const [consented, setConsented] = useState(false);
  const [consentType, setConsentType] = useState("verbal"); // verbal, written, electronic
  const [witnessName, setWitnessName] = useState("");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!consented) {
      setError("Patient consent is required to proceed with screening.");
      return;
    }
    
    setIsSubmitting(true);
    setError(null);
    
    try {
      // Build consent text from the form data
      const consentTextParts = [
        `Patient ${patient.name || patient.id} has provided ${consentType} consent for B12 deficiency screening.`,
        `Consent obtained on ${new Date().toLocaleString()}.`,
        `Purpose: CBC data analysis for B12 deficiency screening, storage of results, and quality improvement.`,
      ];
      if (witnessName && consentType !== "electronic") {
        consentTextParts.push(`Witnessed by: ${witnessName}`);
      }
      if (notes) {
        consentTextParts.push(`Notes: ${notes}`);
      }

      const consentData = {
        patientId: patient.id,
        consentType: "screening", // Type of consent (screening, research, etc.)
        consentMethod: consentType, // Method: verbal, written, electronic
        consentText: consentTextParts.join(" "),
      };

      await onConsentCaptured(consentData);
    } catch (err) {
      setError("Failed to record consent. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
      <div className="bg-slate-50 border-b border-slate-200 px-4 py-3">
        <div className="flex items-center space-x-3">
          <FileCheck className="h-5 w-5 text-teal-600" />
          <h3 className="font-semibold text-slate-800">Patient Consent</h3>
        </div>
      </div>
      
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        {/* Patient Info Summary */}
        <div className="bg-slate-50 rounded-lg p-3">
          <div className="flex items-center space-x-4 text-sm">
            <div className="flex items-center text-slate-600">
              <User className="h-4 w-4 mr-1" />
              <span className="font-medium">{patient.name || "Unknown Patient"}</span>
            </div>
            <div className="text-slate-400">|</div>
            <div className="text-slate-500">ID: {patient.id || "Not assigned"}</div>
            <div className="text-slate-400">|</div>
            <div className="flex items-center text-slate-500">
              <Calendar className="h-4 w-4 mr-1" />
              {new Date().toLocaleDateString()}
            </div>
          </div>
        </div>

        {/* Consent Information */}
        <div className="border border-slate-200 rounded-lg p-4">
          <h4 className="font-medium text-slate-800 mb-2 flex items-center">
            <Shield className="h-4 w-4 mr-2 text-teal-600" />
            Screening Consent Information
          </h4>
          <div className="text-sm text-slate-600 space-y-2">
            <p>By providing consent, the patient acknowledges:</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>Complete Blood Count (CBC) data will be used for B12 deficiency screening</li>
              <li>Results are for clinical decision support only and not a definitive diagnosis</li>
              <li>Screening results will be stored in the patient's medical record</li>
              <li>De-identified data may be used for quality improvement purposes</li>
            </ul>
          </div>
        </div>

        {/* Consent Type */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">Consent Method</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { value: "verbal", label: "Verbal", icon: "🗣️" },
              { value: "written", label: "Written", icon: "✍️" },
              { value: "electronic", label: "Electronic", icon: "📱" },
            ].map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setConsentType(option.value)}
                className={`px-3 py-2 border rounded-md text-sm font-medium transition-colors ${
                  consentType === option.value
                    ? "border-teal-500 bg-teal-50 text-teal-700"
                    : "border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}
              >
                <span className="mr-1">{option.icon}</span> {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Witness Name (for verbal/written) */}
        {consentType !== "electronic" && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Witness / Staff Name
            </label>
            <input
              type="text"
              value={witnessName}
              onChange={(e) => setWitnessName(e.target.value)}
              className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:ring-teal-500 focus:border-teal-500"
              placeholder="Enter name of staff obtaining consent"
            />
          </div>
        )}

        {/* Notes */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Additional Notes (Optional)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:ring-teal-500 focus:border-teal-500"
            placeholder="Any additional notes about consent..."
          />
        </div>

        {/* Consent Checkbox */}
        <div className="bg-teal-50 border border-teal-100 rounded-lg p-4">
          <label className="flex items-start cursor-pointer">
            <input
              type="checkbox"
              checked={consented}
              onChange={(e) => setConsented(e.target.checked)}
              className="mt-1 h-4 w-4 text-teal-600 border-slate-300 rounded focus:ring-teal-500"
            />
            <span className="ml-3 text-sm text-slate-700">
              <span className="font-medium">I confirm</span> that the patient (or their authorized representative) has been informed about the B12 screening process and has provided consent to proceed.
            </span>
          </label>
        </div>

        {error && (
          <div className="flex items-center p-3 bg-red-50 border border-red-100 rounded-md text-sm text-red-600">
            <AlertCircle className="h-4 w-4 mr-2" />
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex space-x-3 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 px-4 py-2 border border-slate-300 text-slate-600 rounded-md text-sm font-medium hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!consented || isSubmitting}
            className="flex-1 px-4 py-2 bg-teal-600 text-white rounded-md text-sm font-medium hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
          >
            {isSubmitting ? (
              "Recording..."
            ) : (
              <><CheckCircle className="h-4 w-4 mr-2" /> Record Consent & Proceed</>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ConsentCapture;
