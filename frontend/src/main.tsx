import { StrictMode, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type Units = 'metric' | 'us';
type Mode = 'fitness' | 'bmi';
type Activity = { id: string; label: string; factor: number };
type Result = {
  measurements: { weight_kg: number; height_cm: number };
  bmi: { value: number; category: string };
  calories?: { resting_kcal: number; maintenance_kcal: number | null; activity_factor: number; formula: string };
};
const initial = { age: '', sex: 'female', weight: '', height: '', feet: '', inches: '', activity: 'moderate' };
const format = (value: number) => value.toLocaleString('en-US');
const rounded = (value: number) => String(Math.round(value * 1000) / 1000);

const calculatorPath = (mode: Mode) => mode === 'bmi' ? '/bmi' : '/calories-bmi';
const modeForPath = (path: string): Mode => path.startsWith('/bmi') ? 'bmi' : 'fitness';

function App() {
  const [units, setUnits] = useState<Units>('metric');
  const [path, setPath] = useState(window.location.pathname);
  const [mode, setMode] = useState<Mode>(() => modeForPath(window.location.pathname));
  const pendingRequest = useRef<AbortController | null>(null);
  const [form, setForm] = useState(initial);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [activityError, setActivityError] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);

  const isMethodPage = path === '/behind-the-numbers';
  const isResultsPage = path.endsWith('/results');
  const knownPath = ['/', '/calories-bmi', '/bmi', '/calories-bmi/results', '/bmi/results', '/behind-the-numbers'].includes(path);

  function applyPath(next: string) {
    pendingRequest.current?.abort();
    pendingRequest.current = null;
    setBusy(false);
    setPath(next);
    setMode(modeForPath(next));
    setError('');
    setResult(null);
    window.scrollTo(0, 0);
  }

  function navigate(next: string) {
    if (window.location.pathname !== next) window.history.pushState(null, '', next);
    applyPath(next);
  }

  useEffect(() => {
    const onPopState = () => applyPath(window.location.pathname);
    window.addEventListener('popstate', onPopState);
    return () => {
      window.removeEventListener('popstate', onPopState);
      pendingRequest.current?.abort();
    };
  }, []);

  useEffect(() => {
    document.title = isMethodPage ? 'Behind the numbers — CalFit' : isResultsPage ? 'Your results — CalFit' : mode === 'bmi' ? 'BMI calculator — CalFit' : 'Calorie & BMI calculator — CalFit';
  }, [path, mode, isMethodPage, isResultsPage]);

  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 10000);
    fetch('/api/activities', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('Activity options unavailable.');
        return response.json();
      })
      .then(data => setActivities(data.activities))
      .catch(() => { if (mounted) setActivityError(true); })
      .finally(() => window.clearTimeout(timer));
    return () => { mounted = false; controller.abort(); window.clearTimeout(timer); };
  }, []);

  function update(field: keyof typeof initial, value: string) {
    setForm(previous => ({ ...previous, [field]: value }));
    setResult(null);
    setError('');
  }

  function changeUnits(next: Units) {
    if (units === next) return;
    setForm(previous => {
      const converted = { ...previous };
      if (previous.weight !== '') {
        converted.weight = rounded(Number(previous.weight) * (next === 'us' ? 1 / 0.45359237 : 0.45359237));
      }
      if (next === 'us' && previous.height !== '') {
        const total = Math.round(Number(previous.height) / 2.54 * 1000) / 1000;
        converted.feet = String(Math.floor(total / 12));
        converted.inches = rounded(total % 12);
      } else if (next === 'us') {
        converted.feet = '';
        converted.inches = '';
      } else if (previous.feet !== '') {
        converted.height = rounded((Number(previous.feet) * 12 + Number(previous.inches)) * 2.54);
      } else {
        converted.height = '';
      }
      return converted;
    });
    setUnits(next);
    setResult(null);
    setError('');
  }

  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setResult(null);
    const controller = new AbortController();
    pendingRequest.current = controller;
    const timer = window.setTimeout(() => controller.abort(), 10000);
    try {
      const payload = {
        units, age: Number(form.age), weight: Number(form.weight),
        height: units === 'metric' ? Number(form.height) : Number(form.feet) * 12 + Number(form.inches),
        ...(mode === 'fitness' ? { sex: form.sex, activity: form.activity } : {}),
      };
      const response = await fetch(`/api/${mode}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload), signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to calculate. Check your details.');
      if (pendingRequest.current !== controller) return;
      const next = calculatorPath(mode) + '/results';
      window.history.pushState(null, '', next);
      setPath(next);
      setResult(data);
      window.scrollTo(0, 0);
      window.setTimeout(() => resultHeading.current?.focus(), 0);
    } catch (failure) {
      if (pendingRequest.current !== controller) return;
      setError(controller.signal.aborted
        ? 'The request timed out. Please try again.'
        : failure instanceof Error ? failure.message : 'Unable to connect. Please try again.');
    } finally {
      window.clearTimeout(timer);
      if (pendingRequest.current === controller) {
        pendingRequest.current = null;
        setBusy(false);
      }
    }
  }

  const calories = result?.calories;
  const energy = calories?.maintenance_kcal ?? calories?.resting_kcal;
  const isResting = calories?.maintenance_kcal === null;
  const bmiPosition = result ? Math.max(0, Math.min(100, (result.bmi.value - 10) / 30 * 100)) : 0;

  return <>
    <header className="site-header">
      <a className="wordmark" href="/" onClick={e => { e.preventDefault(); navigate('/'); }}>CalFit<span className="brand-caption">A little more understanding.</span></a>
      <a className="method-link" href="/behind-the-numbers" onClick={e => { e.preventDefault(); navigate('/behind-the-numbers'); }}>Behind the numbers <span aria-hidden="true">↗</span></a>
    </header>
    <main>
      {!isMethodPage && !isResultsPage && knownPath && <section className="intro" aria-labelledby="page-title">
        <span className="eyebrow"><span className="status-dot" /> YOUR EVERYDAY FITNESS COMPANION</span>
        <h1 id="page-title">Know your body.<br /><em>Find your balance.</em></h1>
        <p>A starting point for understanding your daily energy needs.<br className="desktop-break" /> Simple estimates. A clearer picture. All in one place.</p>
        <div className="intro-meta"><span>01 / Daily calories</span><span>02 / Body mass index</span><span>For adults 20+</span></div>
      </section>}

      {(!knownPath || (isResultsPage && !result)) && <section className="intro"><h1>{knownPath ? 'Let’s calculate again.' : 'Page not found.'}</h1><p>{knownPath ? 'Results aren’t stored. Enter your details to get a fresh estimate.' : 'Choose a calculator to continue.'}</p><button className="calculate-button" onClick={() => navigate(calculatorPath(mode))}>Go to calculator ↗</button></section>}
      {isResultsPage && result && <div className="route-toolbar"><button className="reset-button" onClick={() => navigate(calculatorPath(mode))}>← Edit my details</button><span>Your results</span></div>}
      {!isMethodPage && knownPath && (!isResultsPage || result) && <div className={`calculator-layout ${isResultsPage ? 'results-page' : ''}`} id="calculator">
        {!isResultsPage && <section className="form-card" aria-labelledby="form-title">
          <div className="section-heading"><div><span className="eyebrow">LET’S START WITH YOU</span><h2 id="form-title">Your details</h2></div><span className="step-tag">01 — INPUT</span></div>
          <form onSubmit={calculate}>
            <fieldset disabled={busy}>
              <legend className="sr-only">Fitness calculator details</legend>
              <div className="segmented mode-switch" aria-label="Calculator type">
                {(['fitness', 'bmi'] as Mode[]).map(item => <button key={item} type="button" aria-pressed={mode === item} onClick={() => navigate(calculatorPath(item))}>{item === 'fitness' ? 'Calories + BMI' : 'BMI only'}</button>)}
              </div>
              <div className="units-row"><span>Measurement units</span><div className="segmented" aria-label="Measurement units">
                {(['metric', 'us'] as Units[]).map(item => <button key={item} type="button" aria-pressed={units === item} onClick={() => changeUnits(item)}>{item === 'metric' ? 'Metric' : 'US units'}</button>)}
              </div></div>
              <div className="input-grid">
                <label>Age <span className="input-wrap"><input required name="age" type="number" min="20" max="100" step="1" placeholder="30" value={form.age} onChange={e => update('age', e.target.value)} /><span>years</span></span></label>
                {mode === 'fitness' && <label>Sex used by equation <select name="sex" value={form.sex} onChange={e => update('sex', e.target.value)}><option value="female">Female</option><option value="male">Male</option></select></label>}
                <label>Weight <span className="input-wrap"><input required name="weight" type="number" min="0.01" step="any" placeholder={units === 'metric' ? '70' : '154'} value={form.weight} onChange={e => update('weight', e.target.value)} /><span>{units === 'metric' ? 'kg' : 'lb'}</span></span></label>
                {units === 'metric'
                  ? <label>Height <span className="input-wrap"><input required name="height" type="number" min="100" max="250" step="any" placeholder="175" value={form.height} onChange={e => update('height', e.target.value)} /><span>cm</span></span></label>
                  : <div><span className="field-label">Height</span><div className="height-inputs"><label className="input-wrap"><span className="sr-only">Height feet</span><input required name="feet" type="number" min="0" max="8" step="1" placeholder="5" value={form.feet} onChange={e => update('feet', e.target.value)} /><span>ft</span></label><label className="input-wrap"><span className="sr-only">Height inches</span><input required name="inches" type="number" min="0" max="11.999" step="any" placeholder="9" value={form.inches} onChange={e => update('inches', e.target.value)} /><span>in</span></label></div></div>}
              </div>
              {mode === 'fitness' && <label className="activity-label">Activity level
                <select name="activity" required disabled={!activities.length} value={form.activity} onChange={e => update('activity', e.target.value)}>
                  {!activities.length && <option value="moderate">Loading activity levels…</option>}
                  {activities.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select><span className="field-help">Choose the level that best reflects a typical week.</span>
              </label>}
              {mode === 'fitness' && activityError && <p className="error" role="alert">Could not load activity levels. Check that Flask is running, then refresh this page.</p>}
              {error && <p className="error" role="alert">{error}</p>}
              <div className="form-actions"><button className="calculate-button" disabled={busy || (mode === 'fitness' && !activities.length)} type="submit">{busy ? 'Calculating…' : 'Calculate my results'}<span aria-hidden="true">↗</span></button><button className="reset-button" type="button" onClick={() => { setForm(initial); setUnits('metric'); setResult(null); setError(''); }}>Reset</button></div>
              <p className="privacy-note"><span aria-hidden="true">◇</span> Your measurements are used for this calculation only. We don’t store them.</p>
            </fieldset>
          </form>
        </section>}

        <section className="results" aria-label="Your results" aria-busy={busy}>
          <div className="energy-card">
            <div className="orbit orbit-one" /><div className="orbit orbit-two" />
            <div className="section-heading"><span className="eyebrow">YOUR DAILY ENERGY</span><span className="step-tag">02 — INSIGHT</span></div>
            <h2 ref={resultHeading} tabIndex={-1}>{mode === 'bmi' ? 'A little perspective.' : isResting ? 'Energy at rest.' : 'Fuel for your everyday.'}</h2>
            <div className="energy-value">{energy === undefined ? '—' : format(energy)}<span>kcal / day</span></div>
            <p className="energy-caption">{mode === 'bmi' ? 'Choose Calories + BMI to also estimate your daily energy needs.' : !calories ? 'Add your details to discover your estimated daily calorie needs.' : isResting ? 'Estimated resting energy, before movement and daily activity. This is not a daily intake target.' : 'Estimated maintenance calories — the energy needed to support your current weight.'}</p>
            <div className="energy-bottom"><div><span>Resting energy</span><strong>{calories ? `${format(calories.resting_kcal)} kcal` : '—'}</strong></div><div><span>Activity multiplier</span><strong>{calories ? `${calories.activity_factor}×` : '—'}</strong></div></div>
          </div>
          <div className="bmi-card">
            <div className="section-heading"><div><span className="eyebrow">BODY MASS INDEX</span><h2>Your BMI, in context.</h2></div><span className="small-icon" aria-hidden="true">↗</span></div>
            <div className="bmi-result"><strong>{result ? result.bmi.value.toFixed(2) : '—'}</strong><span className="category-tag">{result ? result.bmi.category : 'Awaiting your details'}</span></div>
            <div className="bmi-scale" aria-hidden="true"><span /><span /><span /><span />{result && <i style={{ left: `${bmiPosition}%` }} />}</div>
            <div className="scale-labels" aria-hidden="true"><span>10</span><span>18.5</span><span>25</span><span>30</span><span>40+</span></div>
            <p>BMI is a screening measure, not a diagnosis. It doesn’t distinguish muscle from body fat.</p>
          </div>
        </section>
      </div>}

      {isMethodPage && <button className="reset-button method-back" onClick={() => navigate('/')}>← Back to calculator</button>}
      {isMethodPage && <section className="method-section" id="method" aria-labelledby="method-title">
        <div><span className="eyebrow">A NOTE ON THE NUMBERS</span><h2 id="method-title">Useful insight.<br /><em>Not the whole story.</em></h2></div>
        <div><p>Calories use the Mifflin–St Jeor equation for resting energy, multiplied by an estimated activity factor. The equation uses male or female coefficients; these don’t describe everyone’s physiology or gender identity.</p><p>BMI divides weight in kilograms by height in metres squared. Categories use the unrounded result, so a rounded value near a boundary may appear in the neighbouring category.</p><details><summary>See formulas and sources</summary><p>Resting kcal/day = 10 × kg + 6.25 × cm − 5 × age + coefficient. Coefficient: +5 for male, −161 for female. Maintenance = resting × activity factor (1.2–1.9).</p><p>BMI = kg ÷ (cm ÷ 100)². Categories: under 18.5 underweight; 18.5 to below 25 healthy weight; 25 to below 30 overweight; 30 or above obesity.</p><p><a href="https://pubmed.ncbi.nlm.nih.gov/2305711/" target="_blank" rel="noreferrer">Mifflin–St Jeor research ↗</a><br /><a href="https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html" target="_blank" rel="noreferrer">CDC adult BMI categories ↗</a></p></details><p className="disclaimer">For adults aged 20–100. Estimates can be less reliable for athletes, older adults, and people with certain health conditions. Not intended for pregnancy or breastfeeding, or as a personalised nutrition prescription.</p></div>
      </section>}
    </main>
    <footer><a className="footer-brand" href="/" onClick={e => { e.preventDefault(); navigate('/'); }}>CalFit<span> Make room for understanding.</span></a><span>Built with care. Backed by clear formulas.</span></footer>
  </>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
