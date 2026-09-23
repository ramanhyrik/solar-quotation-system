// Run with: node tests/test_dashboard_metrics.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const inputs = ['system_value', 'annual_income', 'cumulative_18', 'total_income'].map(
    (calc) => ({ dataset: { calc }, value: '' })
);
const context = vm.createContext({
    document: {
        addEventListener() {},
        querySelectorAll() { return inputs; }
    },
    window: {
        dashboardPricingSettings: {
            leasing_payment_ratio: 1,
            metrics_config: inputs.map((input) => ({
                calculation: input.dataset.calc, label: input.dataset.calc, enabled: true
            }))
        }
    },
    console
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/dashboard.js'), 'utf8'), context);
vm.runInContext(`
    currentQuoteData = { annual_revenue: 13680, total_price: 101250 };
    getFinalQuotePrice = () => 101250;
    getQuoteSystemValue = () => 101250;
    refreshQuoteTextSections = () => {};
`, context);

const inputFor = (calc) => inputs.find((input) => input.dataset.calc === calc);
const edit = (calc, value) => {
    const input = inputFor(calc);
    input.value = value;
    context.onMetricValueInput({ target: input });
    assert.equal(input.value, value, 'Typing must preserve the active input');
};
const total = () => context.resolveQuoteMetrics().find((cube) => cube.calculation === 'total_income');
const checkTotal = (expected) => {
    assert.equal(total().value, expected);
    assert.equal(inputFor('total_income').value, context.formatCurrencyValue(expected));
};

assert.equal(context.computeMetricContext().cumulative_18, 246240);
assert.equal(total().value, 347490);
edit('cumulative_18', '₪200,000');
checkTotal(301250);
edit('system_value', '0');
checkTotal(200000);
edit('cumulative_18', '');
checkTotal(246240);
edit('system_value', '');
checkTotal(347490);
edit('system_value', '₪110,000');
checkTotal(356240);
edit('total_income', '₪400,000');
edit('cumulative_18', '₪200,000');
assert.equal(total().displayValue, '₪400,000', 'Explicit total overrides remain editable');
edit('total_income', '');
assert.equal(total().value, 310000);

vm.runInContext(`quoteMetricOverrides = normalizeOverrides(JSON.stringify({
    system_value: {value: '₪101,250'}, cumulative_18: {value: '₪246,240'}
}));`, context);
assert.equal(total().value, 347490, 'Saved manual values must produce the same total');
console.log('PASS screenshot total, immediate dependent updates, zero, clearing, and saved overrides');
