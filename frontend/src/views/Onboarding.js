import React, { useReducer } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle, Building2, Stethoscope, UserPlus, PartyPopper, ArrowLeft } from "lucide-react";
import { AdminService, BillingService } from "@/services/api";

const STEPS = [
  { id: 1, title: "Add a Lab", icon: Building2, flag: "lab_added" },
  { id: 2, title: "Add a Doctor", icon: Stethoscope, flag: "doctor_added" },
  { id: 3, title: "Invite a User", icon: UserPlus, flag: "user_invited" },
  { id: 4, title: "All Done!", icon: PartyPopper, flag: "completed" },
];

const StepIndicator = ({ current }) => (
  <div className="flex items-center justify-center gap-2 mb-8">
    {STEPS.map((s, i) => (
      <React.Fragment key={s.id}>
        <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold transition-colors ${
          s.id < current ? "bg-teal-500 text-white" :
          s.id === current ? "bg-teal-700 text-white ring-2 ring-teal-200" :
          "bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400"
        }`}>
          {s.id < current ? <CheckCircle className="h-4 w-4" /> : s.id}
        </div>
        {i < STEPS.length - 1 && (
          <div className={`h-0.5 w-8 ${s.id < current ? "bg-teal-400" : "bg-slate-200 dark:bg-slate-700"}`} />
        )}
      </React.Fragment>
    ))}
  </div>
);

const initialState = {
  step: 1,
  loading: false,
  error: null,
  createdLabId: null,
  lab: { code: "", name: "", tier: "standard" },
  doctor: { code: "", name: "", department: "", email: "", lab_id: "" },
  user: { name: "", email: "", username: "", password: "", role: "LAB" },
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_FIELD":
      return { ...state, [action.form]: { ...state[action.form], [action.field]: action.value } };
    case "SET_LOADING":
      return { ...state, loading: action.value };
    case "SET_ERROR":
      return { ...state, error: action.value };
    case "ADVANCE":
      return { ...state, step: state.step + 1, error: null };
    case "GO_BACK":
      return { ...state, step: Math.max(1, state.step - 1), error: null };
    case "SET_CREATED_LAB":
      return { ...state, createdLabId: action.value };
    default:
      return state;
  }
}

const Onboarding = ({ user }) => {
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(reducer, initialState);
  const { step, loading, error, createdLabId, lab, doctor, user: userForm } = state;

  const setField = (form, field, value) => dispatch({ type: "SET_FIELD", form, field, value });

  const markFlag = async (flag) => {
    try {
      await BillingService.updateOnboardingStatus({ [flag]: true });
    } catch {
      // non-critical
    }
  };

  const advanceStep = () => dispatch({ type: "ADVANCE" });

  const handleSkip = async (flag) => {
    await markFlag(flag);
    advanceStep();
  };

  const handleLabSubmit = async (e) => {
    e.preventDefault();
    dispatch({ type: "SET_ERROR", value: null });
    dispatch({ type: "SET_LOADING", value: true });
    try {
      const created = await AdminService.createLab(lab);
      dispatch({ type: "SET_CREATED_LAB", value: created.id });
      await markFlag("lab_added");
      advanceStep();
    } catch (err) {
      dispatch({ type: "SET_ERROR", value: err?.response?.data?.error || "Failed to create lab." });
    } finally {
      dispatch({ type: "SET_LOADING", value: false });
    }
  };

  const handleDoctorSubmit = async (e) => {
    e.preventDefault();
    dispatch({ type: "SET_ERROR", value: null });
    dispatch({ type: "SET_LOADING", value: true });
    try {
      await AdminService.createDoctor({
        ...doctor,
        lab_id: doctor.lab_id || createdLabId,
      });
      await markFlag("doctor_added");
      advanceStep();
    } catch (err) {
      dispatch({ type: "SET_ERROR", value: err?.response?.data?.error || "Failed to create doctor." });
    } finally {
      dispatch({ type: "SET_LOADING", value: false });
    }
  };

  const handleUserSubmit = async (e) => {
    e.preventDefault();
    dispatch({ type: "SET_ERROR", value: null });
    dispatch({ type: "SET_LOADING", value: true });
    try {
      await AdminService.createUser(userForm);
      await markFlag("user_invited");
      advanceStep();
    } catch (err) {
      dispatch({ type: "SET_ERROR", value: err?.response?.data?.error || "Failed to create user." });
    } finally {
      dispatch({ type: "SET_LOADING", value: false });
    }
  };

  const handleFinish = async () => {
    await markFlag("completed");
    navigate("/dashboard");
  };

  const inputCls = "block w-full px-3 py-2.5 border border-slate-300 dark:border-slate-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100";
  const labelCls = "block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1";
  const btnCls = "w-full py-2.5 px-4 bg-teal-700 text-white rounded-lg font-medium text-sm hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

  const currentStep = STEPS[step - 1];
  const StepIcon = currentStep.icon;

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950 flex flex-col justify-center py-12 px-4">
      <div className="sm:mx-auto sm:w-full sm:max-w-lg">
        <div className="flex justify-center mb-2">
          <img src="/logo.png?v=17" alt="Clinomic" className="h-12 w-auto" />
        </div>
        <h2 className="text-center text-2xl font-bold text-slate-900 dark:text-slate-100 mb-1">Welcome to Clinomic</h2>
        <p className="text-center text-sm text-slate-500 dark:text-slate-400 mb-6">Let's set up your organisation in a few steps.</p>

        <StepIndicator current={step} />

        <div className="bg-white dark:bg-slate-900 rounded-xl shadow border border-slate-200 dark:border-slate-700 p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="h-10 w-10 bg-teal-50 dark:bg-teal-900/30 rounded-lg flex items-center justify-center">
              <StepIcon className="h-5 w-5 text-teal-600" />
            </div>
            <div>
              <p className="text-xs text-slate-400 dark:text-slate-500 font-medium">Step {step} of 4</p>
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">{currentStep.title}</h3>
            </div>
          </div>

          {error && (
            <div className="mb-4 text-red-600 text-sm bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          {/* Step 1: Add Lab */}
          {step === 1 && (
            <form onSubmit={handleLabSubmit} className="space-y-4">
              <div>
                <label className={labelCls}>Lab Code</label>
                <input type="text" required value={lab.code} onChange={(e) => setField("lab", "code", e.target.value)} placeholder="LAB-001" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Lab Name</label>
                <input type="text" required value={lab.name} onChange={(e) => setField("lab", "name", e.target.value)} placeholder="City General Hospital" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Tier</label>
                <select value={lab.tier} onChange={(e) => setField("lab", "tier", e.target.value)} className={inputCls}>
                  <option value="standard">Standard</option>
                  <option value="enterprise">Enterprise</option>
                  <option value="pilot">Pilot</option>
                </select>
              </div>
              <button type="submit" disabled={loading} className={btnCls}>
                {loading ? "Creating..." : "Add Lab & Continue"}
              </button>
            </form>
          )}

          {/* Step 2: Add Doctor */}
          {step === 2 && (
            <form onSubmit={handleDoctorSubmit} className="space-y-4">
              <div>
                <label className={labelCls}>Doctor Code</label>
                <input type="text" required value={doctor.code} onChange={(e) => setField("doctor", "code", e.target.value)} placeholder="D001" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Full Name</label>
                <input type="text" required value={doctor.name} onChange={(e) => setField("doctor", "name", e.target.value)} placeholder="Dr. John Doe" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Department</label>
                <input type="text" value={doctor.department} onChange={(e) => setField("doctor", "department", e.target.value)} placeholder="Haematology" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Email</label>
                <input type="email" value={doctor.email} onChange={(e) => setField("doctor", "email", e.target.value)} placeholder="doctor@hospital.com" className={inputCls} />
              </div>
              {!createdLabId && (
                <div>
                  <label className={labelCls}>Lab ID</label>
                  <input type="text" required value={doctor.lab_id} onChange={(e) => setField("doctor", "lab_id", e.target.value)} placeholder="Lab UUID" className={inputCls} />
                </div>
              )}
              <button type="submit" disabled={loading} className={btnCls}>
                {loading ? "Creating..." : "Add Doctor & Continue"}
              </button>
            </form>
          )}

          {/* Step 3: Invite User */}
          {step === 3 && (
            <form onSubmit={handleUserSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Full Name</label>
                  <input type="text" required value={userForm.name} onChange={(e) => setField("user", "name", e.target.value)} placeholder="Jane Doe" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Email</label>
                  <input type="email" value={userForm.email} onChange={(e) => setField("user", "email", e.target.value)} placeholder="jane@hospital.com" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Username</label>
                  <input type="text" required value={userForm.username} onChange={(e) => setField("user", "username", e.target.value)} placeholder="jane.doe" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Password</label>
                  <input type="password" required value={userForm.password} onChange={(e) => setField("user", "password", e.target.value)} placeholder="Min 8 chars" className={inputCls} />
                </div>
              </div>
              <div>
                <label className={labelCls}>Role</label>
                <select value={userForm.role} onChange={(e) => setField("user", "role", e.target.value)} className={inputCls}>
                  <option value="LAB">Lab Technician</option>
                  <option value="DOCTOR">Doctor</option>
                  <option value="ADMIN">Admin</option>
                </select>
              </div>
              <button type="submit" disabled={loading} className={btnCls}>
                {loading ? "Creating..." : "Invite User & Continue"}
              </button>
            </form>
          )}

          {/* Step 4: Done */}
          {step === 4 && (
            <div className="text-center py-4">
              <div className="flex justify-center mb-4">
                <div className="h-16 w-16 bg-teal-50 dark:bg-teal-900/30 rounded-full flex items-center justify-center">
                  <CheckCircle className="h-10 w-10 text-teal-500" />
                </div>
              </div>
              <h3 className="text-xl font-semibold text-slate-800 dark:text-slate-100 mb-2">You're all set!</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">Your organisation is ready. Head to the dashboard to start screening.</p>
              <button onClick={handleFinish} className={btnCls}>
                Go to Dashboard
              </button>
            </div>
          )}

          {step < 4 && (
            <div className="flex items-center justify-between mt-3">
              {step > 1 ? (
                <button
                  type="button"
                  onClick={() => dispatch({ type: "GO_BACK" })}
                  className="inline-flex items-center gap-1 py-2 text-sm text-slate-400 hover:text-slate-600 transition-colors"
                >
                  <ArrowLeft className="h-4 w-4" /> Back
                </button>
              ) : (
                <span />
              )}
              <button
                type="button"
                onClick={() => handleSkip(currentStep.flag)}
                className="py-2 text-sm text-slate-400 hover:text-slate-600 transition-colors"
              >
                Skip this step
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Onboarding;
