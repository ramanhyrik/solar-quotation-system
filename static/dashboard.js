let currentQuoteData = {};
let currentOfferImageUrl = null;
const SYSTEM_VALUE_AMORTIZATION_YEARS = 25;

function setOfferImagePreview(url) {
    currentOfferImageUrl = url || null;
    const wrap = document.getElementById('offerImagePreviewWrap');
    const img = document.getElementById('offerImagePreview');
    if (!wrap || !img) return;
    if (currentOfferImageUrl) {
        img.src = currentOfferImageUrl;
        wrap.style.display = 'block';
    } else {
        img.src = '';
        wrap.style.display = 'none';
    }
}

async function uploadOfferImage(file) {
    const status = document.getElementById('offerImageStatus');
    if (status) status.textContent = 'מעלה תמונה...';

    const formData = new FormData();
    formData.append('image', file);

    try {
        const response = await fetch('/api/quote-image/upload', { method: 'POST', body: formData });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Upload failed');
        }
        const data = await response.json();
        setOfferImagePreview(data.image_url);
        if (status) status.textContent = 'התמונה הועלתה בהצלחה';
    } catch (error) {
        console.error('[offer-image] upload failed', error);
        if (status) status.textContent = `שגיאה בהעלאת התמונה: ${error.message}`;
    }
}

function registerOfferImageHandlers() {
    const fileInput = document.getElementById('offerImageFile');
    const removeBtn = document.getElementById('offerImageRemoveBtn');
    if (fileInput) {
        fileInput.addEventListener('change', (event) => {
            const file = event.target.files && event.target.files[0];
            if (file) uploadOfferImage(file);
        });
    }
    if (removeBtn) {
        removeBtn.addEventListener('click', () => {
            setOfferImagePreview(null);
            if (fileInput) fileInput.value = '';
            const status = document.getElementById('offerImageStatus');
            if (status) status.textContent = '';
        });
    }

    // Paste an image straight from the clipboard (Ctrl+V) while the quote form
    // is open — in addition to the file picker.
    document.addEventListener('paste', (event) => {
        const quoteSection = document.getElementById('quoteSection');
        if (!document.getElementById('offerImageFile') || (quoteSection && quoteSection.style.display === 'none')) {
            return;
        }
        const items = (event.clipboardData && event.clipboardData.items) || [];
        for (const item of items) {
            if (item.type && item.type.indexOf('image') === 0) {
                const file = item.getAsFile();
                if (file) {
                    event.preventDefault();
                    const status = document.getElementById('offerImageStatus');
                    if (status) status.textContent = 'מעלה תמונה מהלוח...';
                    uploadOfferImage(file);
                }
                break;
            }
        }
    });
}

const quoteTemplateFieldMap = {
    basicAssumptionsText: 'basic_assumptions_default',
    revenueCalculationText: 'revenue_calculation_default',
    summaryText: 'summary_default',
    environmentalImpactText: 'environmental_impact_default'
};

function getDashboardPricingSettings() {
    return window.dashboardPricingSettings || {};
}

function parseNumericInput(value) {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function formatInteger(value) {
    const parsed = Number(value || 0);
    return Math.round(parsed).toLocaleString();
}

function renderTemplateString(template, context) {
    if (!template) {
        return '';
    }

    return String(template).replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key) => {
        const value = context[key];
        return value === undefined || value === null ? '' : String(value);
    });
}

function buildQuoteTemplateContext() {
    const pricing = getDashboardPricingSettings();
    const systemSize = parseNumericInput(document.getElementById('systemSize')?.value);
    const roofArea = parseNumericInput(document.getElementById('roofArea')?.value);
    const annualProduction = Number(currentQuoteData.annual_production || 0);
    const grossAnnualRevenue = Number(currentQuoteData.annual_revenue || 0);
    const totalPrice = getFinalQuotePrice() || Number(currentQuoteData.total_price || 0);
    const metricContext = computeMetricContext();
    const systemValueAfter25Years = metricContext.system_value;
    const treesMultiplier = Number(pricing.trees_multiplier ?? 0.05);
    const degradationRate = Number(pricing.degradation_rate ?? 0.004);
    const operatingCostBase = Number(pricing.operating_cost_base ?? 0.005);
    const operatingCostIncrease = Number(pricing.operating_cost_increase ?? 0.02);
    const configuredTariff = Number(pricing.tariff_rate ?? 0.48);
    const urbanPremium = !!document.getElementById('urbanPremium')?.checked;
    // Tiered tariff: first 22.5 kW at the standard/premium rate, rest at 0.38.
    const firstTierRate = urbanPremium ? 0.52 : configuredTariff;
    const secondTierRate = 0.38;
    const thresholdKw = 22.5;

    return {
        system_size: systemSize !== null ? systemSize.toFixed(1).replace(/\.0$/, '') : '',
        roof_area: roofArea !== null ? roofArea.toFixed(1).replace(/\.0$/, '') : '',
        annual_production: formatInteger(annualProduction),
        // Keep the legacy placeholder name used by saved templates, but bind it
        // to the same value shown in the annual-income cube.
        annual_revenue: metricDisplayForCalc('annual_income'),
        gross_annual_revenue: formatInteger(grossAnnualRevenue),
        total_price: formatInteger(totalPrice),
        system_value_after_25_years: formatInteger(systemValueAfter25Years),
        trees: formatInteger(annualProduction * treesMultiplier),
        co2_saved: formatInteger(annualProduction * 0.5),
        total_cashflow_25: metricDisplayForCalc('cumulative_25'),
        quarterly_value: metricDisplayForCalc('quarterly_value'),
        tariff_rate: firstTierRate.toFixed(2),
        tariff_agorot: formatInteger(firstTierRate * 100),
        tariff_first_agorot: formatInteger(firstTierRate * 100),
        tariff_second_agorot: formatInteger(secondTierRate * 100),
        tariff_threshold_kw: thresholdKw.toFixed(1).replace(/\.0$/, ''),
        degradation_rate_percent: (degradationRate * 100).toFixed(1).replace(/\.0$/, ''),
        operating_cost_base_percent: (operatingCostBase * 100).toFixed(1).replace(/\.0$/, ''),
        operating_cost_increase_percent: (operatingCostIncrease * 100).toFixed(1).replace(/\.0$/, '')
    };
}

function initializeQuoteTextDefaults() {
    const pricing = getDashboardPricingSettings();

    Object.entries(quoteTemplateFieldMap).forEach(([fieldId, pricingKey]) => {
        const field = document.getElementById(fieldId);
        if (!field) {
            return;
        }

        const template = pricing[pricingKey] || '';
        field.dataset.template = template;

        if (!field.value.trim()) {
            field.value = template;
            field.dataset.autoFilled = 'true';
        }
    });
}

function refreshQuoteTextSections(force = false) {
    const context = buildQuoteTemplateContext();

    Object.entries(quoteTemplateFieldMap).forEach(([fieldId, pricingKey]) => {
        const field = document.getElementById(fieldId);
        if (!field) {
            return;
        }

        const template = field.dataset.template || getDashboardPricingSettings()[pricingKey] || '';
        field.dataset.template = template;

        if (!template) {
            return;
        }

        const shouldReplace = force || field.dataset.userEdited !== 'true' || !field.value.trim();
        if (shouldReplace) {
            field.value = renderTemplateString(template, context);
            field.dataset.autoFilled = 'true';
            field.dataset.userEdited = 'false';
        }
    });
}

function updateManualPriceDisplay() {
    const totalPriceElement = document.getElementById('totalPrice');
    if (!totalPriceElement) {
        return;
    }

    const manualPrice = getFinalQuotePrice();
    const fallbackPrice = Number(currentQuoteData.total_price || 0);
    const priceToShow = manualPrice || fallbackPrice;
    totalPriceElement.textContent = `₪${formatInteger(priceToShow)}`;
}

function getQuotePricePerKw() {
    const field = document.getElementById('pricePerKw');
    return parseNumericInput(field?.value);
}

function getQuoteSystemSize() {
    return parseNumericInput(document.getElementById('systemSize')?.value);
}

function getQuoteSystemValue() {
    const pricePerKw = getQuotePricePerKw();
    const systemSize = getQuoteSystemSize();
    if (!pricePerKw || !systemSize) {
        return null;
    }
    return Math.round(pricePerKw * systemSize);
}

function updateSystemValueDisplay() {
    const display = document.getElementById('systemValueDisplay');
    if (!display) {
        return;
    }
    const value = getQuoteSystemValue();
    display.textContent = value ? `₪${formatInteger(value)}` : '₪0';
}

function maybePrefillPricePerKw() {
    const field = document.getElementById('pricePerKw');
    if (!field) {
        return;
    }

    const isEditable = field.dataset.userEdited === 'true' && field.value.trim();
    const systemSize = getQuoteSystemSize();
    if (!isEditable && currentQuoteData.total_price && systemSize) {
        field.value = (Number(currentQuoteData.total_price) / systemSize).toFixed(2);
        field.dataset.autoFilled = 'true';
    }
    updateSystemValueDisplay();
}

function getFinalQuotePrice() {
    const finalPriceField = document.getElementById('finalPrice');
    return parseNumericInput(finalPriceField?.value);
}

// ---- Financial metric cubes (configured in the admin panel) ----
const DEFAULT_METRICS_CONFIG = [
    { label: 'הכנסה שנתית', calculation: 'annual_income', enabled: true },
    { label: 'ערך רבעוני משוער', calculation: 'quarterly_value', enabled: true },
    { label: 'תזרים מצטבר ל-25 שנה', calculation: 'cumulative_25', enabled: true },
    { label: 'שווי מערכת לאחר 25 שנה', calculation: 'system_value', enabled: true },
    { label: 'סך הכנסה', calculation: 'total_income', enabled: true }
];
const LEGACY_OVERRIDE_ORDER = ['annual_income', 'cumulative_25', 'system_value', 'total_income'];

// Per-quote overrides, keyed by calculation. Preserved from saved quotes so the
// editor preview matches the PDF; the cubes themselves are managed in the admin
// panel, so this preview is read-only.
let quoteMetricOverrides = {};

function formatCurrencyValue(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num)) return '';
    return `₪${Math.round(num).toLocaleString()}`;
}

function getMetricsConfig() {
    const cfg = getDashboardPricingSettings().metrics_config;
    const list = Array.isArray(cfg) && cfg.length ? cfg : DEFAULT_METRICS_CONFIG;
    return list.filter((c) => c && c.calculation && c.enabled !== false);
}

// Mirror of metrics_catalog.build_metric_context (server) so the editor
// preview, the text sections and the PDF always agree.
function computeMetricContext() {
    const pricing = getDashboardPricingSettings();
    const annualRevenue = Number(currentQuoteData.annual_revenue || 0);
    const leasingRatio = Number(pricing.leasing_payment_ratio ?? 0.25);
    const degradationRate = Number(pricing.degradation_rate ?? 0.004);
    const totalPrice = getFinalQuotePrice() || Number(currentQuoteData.total_price || 0);
    const systemValue = getQuoteSystemValue() || totalPrice || 0;

    let cumulative = 0;
    for (let year = 0; year < 25; year++) {
        cumulative += annualRevenue * Math.max(0, 1 - (degradationRate * year)) * leasingRatio;
    }
    cumulative = Math.round(cumulative);

    const annualIncome = annualRevenue * leasingRatio;
    const totalIncome = systemValue + cumulative;
    return {
        gross_annual_revenue: annualRevenue,
        annual_income: annualIncome,
        monthly_income: annualIncome / 12,
        quarterly_income: annualIncome / 4,
        cumulative_25: cumulative,
        system_value: systemValue,
        total_income: totalIncome,
        quarterly_value: totalIncome / SYSTEM_VALUE_AMORTIZATION_YEARS / 4
    };
}

function computeCubeValue(calc, context) {
    const v = context[calc];
    return Number.isFinite(v) ? v : 0;
}

// Resolve the cubes for the current quote (config + per-quote overrides).
function resolveQuoteMetrics() {
    const context = computeMetricContext();
    return getMetricsConfig().map((cube) => {
        const override = quoteMetricOverrides[cube.calculation] || {};
        const computed = computeCubeValue(cube.calculation, context);
        const hasOverrideValue = String(override.value || '').trim() !== '';
        return {
            calculation: cube.calculation,
            label: String(override.label || '').trim() || cube.label,
            value: computed,
            displayValue: hasOverrideValue
                ? String(override.value).trim()
                : formatCurrencyValue(computed)
        };
    });
}

// Value (₪ stripped) for a given calculation, used by the text templates.
function metricDisplayForCalc(calc) {
    const cube = resolveQuoteMetrics().find((c) => c.calculation === calc);
    if (cube) return cube.displayValue.replace(/^\s*₪\s*/, '');
    return formatInteger(computeCubeValue(calc, computeMetricContext()));
}

// Render the cube list from the current config. Labels/order/calculations are
// managed in the admin panel; the VALUE of each cube is editable per quote and
// saved as an override (empty or unchanged = auto-computed).
function refreshMetricDefaults() {
    const container = document.getElementById('financialMetricsEditor');
    if (!container) return;
    container.innerHTML = '';
    resolveQuoteMetrics().forEach((cube) => {
        const row = document.createElement('div');
        row.className = 'metric-preview-row';
        row.style.cssText = 'display:flex; align-items:center; gap:10px; padding:8px 12px; border:1px solid rgba(58,228,120,0.25); border-radius:8px; margin-bottom:8px; background:rgba(20,24,31,0.5);';
        const label = document.createElement('span');
        label.style.cssText = 'flex:1; color:#A0AEC0;';
        label.textContent = cube.label;
        const value = document.createElement('input');
        value.type = 'text';
        value.className = 'metric-value-input';
        value.dataset.calc = cube.calculation;
        value.value = cube.displayValue;
        value.title = 'ניתן לערוך את הסכום ידנית';
        value.style.cssText = 'width:150px; text-align:left; padding:6px 10px; border:2px solid rgba(58,228,120,0.3); border-radius:6px; background:rgba(20,24,31,0.7); color:#fff; font-weight:600;';
        value.addEventListener('input', onMetricValueInput);
        row.appendChild(label);
        row.appendChild(value);
        container.appendChild(row);
    });
}

function onMetricValueInput(event) {
    const el = event.target;
    const calc = el.dataset.calc;
    const raw = (el.value || '').trim();
    const computed = formatCurrencyValue(computeCubeValue(calc, computeMetricContext()));
    if (!raw || raw === computed) {
        delete quoteMetricOverrides[calc];
    } else {
        quoteMetricOverrides[calc] = Object.assign({}, quoteMetricOverrides[calc], { value: raw });
    }
    refreshQuoteTextSections(true);
}

function normalizeOverrides(saved) {
    let data = saved;
    if (typeof data === 'string') {
        try { data = JSON.parse(data); } catch (_) { return {}; }
    }
    if (data && !Array.isArray(data) && typeof data === 'object') {
        const out = {};
        Object.keys(data).forEach((key) => {
            if (data[key] && typeof data[key] === 'object') out[key] = data[key];
        });
        return out;
    }
    if (Array.isArray(data)) {
        const out = {};
        data.forEach((item, index) => {
            if (index >= LEGACY_OVERRIDE_ORDER.length || !item) return;
            if (item.label || (item.value !== undefined && item.value !== '')) {
                out[LEGACY_OVERRIDE_ORDER[index]] = item;
            }
        });
        return out;
    }
    return {};
}

function populateMetricOverrides(saved) {
    quoteMetricOverrides = normalizeOverrides(saved);
    refreshMetricDefaults();
}

function collectMetricOverrides() {
    return Object.keys(quoteMetricOverrides).length ? quoteMetricOverrides : null;
}

function collectQuotePayload() {
    const customerName = document.getElementById('customerName').value;
    const systemSize = parseNumericInput(document.getElementById('systemSize').value);

    if (!customerName || !systemSize) {
        throw new Error('missing_required_fields');
    }

    if (!currentQuoteData.total_price) {
        throw new Error('quote_not_calculated');
    }

    // Persist the current synchronized values, including metric edits made
    // immediately before saving.
    refreshQuoteTextSections(true);

    return {
        customer_name: customerName,
        customer_phone: document.getElementById('customerPhone').value,
        customer_email: document.getElementById('customerEmail').value,
        customer_address: document.getElementById('customerAddress').value,
        system_size: systemSize,
        roof_area: parseNumericInput(document.getElementById('roofArea').value),
        annual_production: currentQuoteData.annual_production,
        total_price: getFinalQuotePrice() || currentQuoteData.total_price,
        maintenance: document.getElementById('maintenance').value || null,
        service: document.getElementById('service').value || null,
        system_value_after_25_years: getQuoteSystemValue(),
        price_per_kwp_quote: getQuotePricePerKw(),
        offer_image_path: currentOfferImageUrl,
        financial_metrics_overrides: collectMetricOverrides(),
        basic_assumptions_text: document.getElementById('basicAssumptionsText').value,
        revenue_calculation_text: document.getElementById('revenueCalculationText').value,
        summary_text: document.getElementById('summaryText').value,
        environmental_impact_text: document.getElementById('environmentalImpactText').value,
        annual_revenue: currentQuoteData.annual_revenue,
        payback_period: currentQuoteData.payback_period,
        model_type: window.currentModel || 'purchase',
        urban_premium: !!document.getElementById('urbanPremium')?.checked
    };
}

function resetQuoteForm() {
    const formIds = [
        'customerName',
        'customerPhone',
        'customerEmail',
        'customerAddress',
        'systemSize',
        'roofArea',
        'finalPrice',
        'maintenance',
        'service',
        'pricePerKw',
        'basicAssumptionsText',
        'revenueCalculationText',
        'summaryText',
        'environmentalImpactText'
    ];

    formIds.forEach((id) => {
        const field = document.getElementById(id);
        if (!field) {
            return;
        }

        field.value = '';
        field.dataset.userEdited = 'false';
        field.dataset.autoFilled = 'false';
    });

    const urbanPremiumField = document.getElementById('urbanPremium');
    if (urbanPremiumField) urbanPremiumField.checked = false;
    document.getElementById('calculations').style.display = 'none';
    currentQuoteData = {};
    quoteMetricOverrides = {};
    refreshMetricDefaults();
    setOfferImagePreview(null);
    const offerImageFile = document.getElementById('offerImageFile');
    if (offerImageFile) offerImageFile.value = '';
    const offerImageStatus = document.getElementById('offerImageStatus');
    if (offerImageStatus) offerImageStatus.textContent = '';
    initializeQuoteTextDefaults();
}

function markFieldAsEdited(event) {
    event.target.dataset.userEdited = 'true';
    event.target.dataset.autoFilled = 'false';
}

function registerQuoteFieldListeners() {
    [
        'basicAssumptionsText',
        'revenueCalculationText',
        'summaryText',
        'environmentalImpactText',
        'finalPrice',
        'pricePerKw'
    ].forEach((fieldId) => {
        const field = document.getElementById(fieldId);
        if (!field) {
            return;
        }

        field.addEventListener('input', (event) => {
            markFieldAsEdited(event);
            if (fieldId === 'finalPrice') {
                updateManualPriceDisplay();
            }
            if (fieldId === 'pricePerKw') {
                updateSystemValueDisplay();
                refreshMetricDefaults();
                refreshQuoteTextSections(true);
            }
        });
    });

    const systemSizeField = document.getElementById('systemSize');
    if (systemSizeField) {
        systemSizeField.addEventListener('input', () => {
            updateSystemValueDisplay();
            refreshMetricDefaults();
            refreshQuoteTextSections(true);
        });
    }

    const urbanPremiumField = document.getElementById('urbanPremium');
    if (urbanPremiumField) {
        urbanPremiumField.addEventListener('change', () => {
            // Re-run the (tiered) calculation so revenue/cubes reflect the toggle.
            if (parseNumericInput(document.getElementById('systemSize')?.value)) {
                calculateQuote();
            }
        });
    }
}

async function calculateQuote() {
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!systemSize || systemSize <= 0) {
        alert('נא להזין גודל מערכת תקין');
        return;
    }

    try {
        const urbanPremium = !!document.getElementById('urbanPremium')?.checked;
        const formData = new FormData();
        formData.append('system_size', systemSize);
        formData.append('urban_premium', urbanPremium);

        const response = await fetch('/api/calculate', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        currentQuoteData = {
            total_price: data.total_price,
            annual_revenue: data.annual_revenue,
            tariff_rate: data.tariff_rate,
            payback_period: data.payback_period,
            annual_production: data.annual_production,
            urban_premium: urbanPremium
        };

        const finalPriceField = document.getElementById('finalPrice');
        if (finalPriceField && (!finalPriceField.value.trim() || finalPriceField.dataset.userEdited !== 'true')) {
            finalPriceField.value = Math.round(data.total_price);
            finalPriceField.dataset.autoFilled = 'true';
            finalPriceField.dataset.userEdited = 'false';
        }

        maybePrefillPricePerKw();
        refreshMetricDefaults();
        refreshQuoteTextSections(true);

        document.getElementById('annualRevenue').textContent = `₪${formatInteger(computeMetricContext().annual_income)}`;
        document.getElementById('annualProduction').textContent = `${formatInteger(data.annual_production)} קוט״ש`;
        updateManualPriceDisplay();
        document.getElementById('calculations').style.display = 'grid';
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בחישוב ההצעה');
    }
}

async function saveQuote() {
    let quoteData;
    try {
        quoteData = collectQuotePayload();
    } catch (error) {
        if (error.message === 'missing_required_fields') {
            alert('נא למלא שדות חובה (שם לקוח וגודל מערכת)');
            return;
        }
        alert('נא לחשב את ההצעה קודם');
        return;
    }

    try {
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quoteData)
        });

        if (response.ok) {
            alert('ההצעה נשמרה בהצלחה!');
            resetQuoteForm();
        } else {
            alert('שגיאה בשמירת ההצעה');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בשמירת ההצעה');
    }
}

function populateQuoteForm(quote) {
    if (typeof setQuoteModel === 'function') {
        setQuoteModel(quote.model_type || 'purchase');
    } else {
        window.currentModel = quote.model_type || 'purchase';
    }

    document.getElementById('customerName').value = quote.customer_name || '';
    document.getElementById('customerPhone').value = quote.customer_phone || '';
    document.getElementById('customerEmail').value = quote.customer_email || '';
    document.getElementById('customerAddress').value = quote.customer_address || '';
    document.getElementById('systemSize').value = quote.system_size || '';
    document.getElementById('roofArea').value = quote.roof_area || '';
    const finalPriceField = document.getElementById('finalPrice');
    if (finalPriceField) finalPriceField.value = quote.total_price || '';
    document.getElementById('maintenance').value = quote.maintenance || '';
    document.getElementById('service').value = quote.service || '';
    const pricePerKwField = document.getElementById('pricePerKw');
    if (pricePerKwField) {
        const storedSystemSize = Number(quote.system_size || 0);
        const storedSystemValue = Number(quote.system_value_after_25_years || 0);
        if (quote.price_per_kwp_quote) {
            pricePerKwField.value = quote.price_per_kwp_quote;
        } else if (storedSystemValue && storedSystemSize) {
            pricePerKwField.value = (storedSystemValue / storedSystemSize).toFixed(2);
        } else {
            pricePerKwField.value = '';
        }
        updateSystemValueDisplay();
    }
    document.getElementById('basicAssumptionsText').value = quote.basic_assumptions_text || '';
    document.getElementById('revenueCalculationText').value = quote.revenue_calculation_text || '';
    document.getElementById('summaryText').value = quote.summary_text || '';
    document.getElementById('environmentalImpactText').value = quote.environmental_impact_text || '';
    setOfferImagePreview(quote.offer_image_path || null);
    const offerImageFile = document.getElementById('offerImageFile');
    if (offerImageFile) offerImageFile.value = '';
    const urbanPremiumField = document.getElementById('urbanPremium');
    if (urbanPremiumField) urbanPremiumField.checked = !!quote.urban_premium;
    currentQuoteData = {
        total_price: Number(quote.total_price || 0),
        annual_revenue: Number(quote.annual_revenue || 0),
        tariff_rate: Number(quote.tariff_rate || getDashboardPricingSettings().tariff_rate || 0.48),
        payback_period: Number(quote.payback_period || 0),
        annual_production: Number(quote.annual_production || 0),
        urban_premium: !!quote.urban_premium
    };
    populateMetricOverrides(quote.financial_metrics_overrides);

    ['finalPrice', 'pricePerKw', 'basicAssumptionsText', 'revenueCalculationText', 'summaryText', 'environmentalImpactText']
        .forEach((id) => {
            const field = document.getElementById(id);
            if (field) {
                field.dataset.userEdited = 'true';
                field.dataset.autoFilled = 'false';
            }
        });

    updateManualPriceDisplay();
    document.getElementById('annualRevenue').textContent = `₪${formatInteger(computeMetricContext().annual_income)}`;
    document.getElementById('annualProduction').textContent = `${formatInteger(quote.annual_production || 0)} קוט״ש`;
    document.getElementById('calculations').style.display = 'grid';
}

async function loadQuoteIntoForm(quoteId) {
    try {
        const response = await fetch(`/api/quotes/${quoteId}`);
        if (!response.ok) {
            throw new Error('Failed to load quote');
        }

        const quote = await response.json();
        populateQuoteForm(quote);

        if (typeof showSection === 'function') {
            showSection('quote');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בטעינת ההצעה');
    }
}

let allQuotes = [];

function formatQuoteDateTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (isNaN(date.getTime())) return value;
    return date.toLocaleString('he-IL', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

function renderQuoteHistory(quotes) {
    const tbody = document.querySelector('#quotesTable tbody');
    tbody.innerHTML = '';

    quotes.forEach((quote) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong style="color: #00358A; font-size: 16px;">${quote.id}</strong></td>
            <td>${quote.quote_number}</td>
            <td>${quote.customer_name}</td>
            <td>${quote.system_size} קילוואט</td>
            <td>₪${Number(quote.total_price || 0).toLocaleString()}</td>
            <td>${formatQuoteDateTime(quote.created_at)}</td>
            <td>
                <div style="display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap; align-items: center;">
                    <button onclick="loadQuoteIntoForm(${quote.id})" style="background: #3AE478; color: #14181F; padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap;">טען</button>
                    <button onclick="generateSignatureLink(${quote.id})" style="background: #28a745; color: white; padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap;">קישור חתימה</button>
                    <button onclick="viewQuoteAnalysis(${quote.id})" style="background: #D9FF0D; color: #00358A; padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap;">ניתוח פיננסי</button>
                    <button onclick="downloadPDF(${quote.id})" style="background: #00358A; color: white; padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap;">PDF</button>
                    <button onclick="deleteQuote(${quote.id})" style="background: #dc2626; color: white; padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; white-space: nowrap;">מחק</button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function filterQuoteHistory() {
    const input = document.getElementById('quoteSearchInput');
    const term = (input ? input.value : '').trim().toLowerCase();

    if (!term) {
        renderQuoteHistory(allQuotes);
        return;
    }

    const filtered = allQuotes.filter((quote) => {
        const haystack = [
            quote.quote_number,
            quote.customer_name,
            quote.system_size,
            quote.id
        ].map((v) => String(v == null ? '' : v).toLowerCase());
        return haystack.some((v) => v.includes(term));
    });

    renderQuoteHistory(filtered);
}

async function loadQuoteHistory() {
    try {
        const response = await fetch('/api/quotes');
        const data = await response.json();

        allQuotes = data.quotes || [];
        filterQuoteHistory();
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בטעינת היסטוריית ההצעות');
    }
}

async function deleteQuote(id) {
    if (!confirm('האם אתה בטוח שברצונך למחוק הצעה זו?')) {
        return;
    }

    try {
        const response = await fetch(`/api/quotes/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadQuoteHistory();
        } else {
            alert('שגיאה במחיקת ההצעה');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה במחיקת ההצעה');
    }
}

function downloadPDF(quoteId) {
    window.location.href = `/api/quotes/${quoteId}/pdf`;
}

async function generateSignatureLink(quoteId) {
    try {
        const response = await fetch(`/api/quotes/${quoteId}/generate-signature-link`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Failed to generate signature link');
        }

        const data = await response.json();
        const modal = document.createElement('div');
        modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 10000;';

        modal.innerHTML = `
            <div style="background: white; padding: 30px; border-radius: 12px; max-width: 600px; width: 90%; direction: rtl;">
                <h2 style="color: #00358A; margin-bottom: 20px;">קישור חתימה נוצר בהצלחה!</h2>
                <div style="background: #f7fafc; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <strong style="display: block; margin-bottom: 10px; color: #2d3748;">פרטי ההצעה:</strong>
                    <div style="font-size: 14px; color: #4a5568; line-height: 1.8;">
                        מספר ההצעה: <strong>${data.quote_number}</strong><br>
                        לקוח: <strong>${data.customer_name}</strong><br>
                        אימייל: <strong>${data.customer_email || 'לא צוין'}</strong>
                    </div>
                </div>
                <div style="background: #e8f4f8; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #00358A;">
                    <strong style="display: block; margin-bottom: 10px; color: #00358A;">קישור לחתימה:</strong>
                    <input type="text" value="${data.full_url}" readonly
                           style="width: 100%; padding: 10px; border: 2px solid #00358A; border-radius: 6px; font-size: 13px; font-family: monospace;"
                           id="signatureLinkInput">
                </div>
                <div style="display: flex; gap: 10px;">
                    <button onclick="copySignatureLink(event)"
                            style="flex: 1; padding: 12px; background: #28a745; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">
                        העתק קישור
                    </button>
                    <button onclick="closeSignatureModal()"
                            style="flex: 1; padding: 12px; background: #6c757d; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">
                        סגור
                    </button>
                </div>
                <div style="margin-top: 15px; padding: 12px; background: #fff3cd; border-radius: 6px; font-size: 13px; color: #856404;">
                    הקישור תקף ל-30 יום
                </div>
            </div>
        `;

        document.body.appendChild(modal);
        window.currentSignatureModal = modal;

        setTimeout(() => {
            document.getElementById('signatureLinkInput').select();
        }, 100);
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה ביצירת קישור חתימה');
    }
}

async function copySignatureLink(event) {
    const input = document.getElementById('signatureLinkInput');

    try {
        await navigator.clipboard.writeText(input.value);
    } catch (error) {
        input.select();
        document.execCommand('copy');
    }

    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = 'הועתק!';
    btn.style.background = '#00358A';

    setTimeout(() => {
        btn.textContent = originalText;
        btn.style.background = '#28a745';
    }, 2000);
}

function closeSignatureModal() {
    if (window.currentSignatureModal) {
        window.currentSignatureModal.remove();
        window.currentSignatureModal = null;
    }
}

async function viewQuoteAnalysis(quoteId) {
    try {
        const response = await fetch(`/api/quotes/${quoteId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch quote');
        }

        const quote = await response.json();
        if (typeof calculateFinancialComparison === 'function') {
            await calculateFinancialComparison(quote.system_size, quote.total_price);
            if (typeof showSection === 'function') {
                showSection('comparison');
            }
        } else {
            alert('פונקציית הניתוח הפיננסי לא זמינה');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בטעינת ניתוח פיננסי');
    }
}

async function generatePDF() {
    let quoteData;
    try {
        quoteData = collectQuotePayload();
    } catch (error) {
        if (error.message === 'missing_required_fields') {
            alert('נא למלא שדות חובה (שם לקוח וגודל מערכת) ולחשב קודם');
            return;
        }
        alert('נא לחשב את ההצעה קודם');
        return;
    }

    try {
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quoteData)
        });

        if (!response.ok) {
            throw new Error('Failed to save quote');
        }

        const result = await response.json();
        window.location.href = `/api/quotes/${result.quote_id}/pdf`;
        alert('ה-PDF נוצר ומוריד!');
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה ביצירת PDF. נסה שוב.');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    registerQuoteFieldListeners();
    registerOfferImageHandlers();
    initializeQuoteTextDefaults();
});
