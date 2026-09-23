const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const fields = new Map();
const field = (id) => {
    if (!fields.has(id)) fields.set(id, {value: '', checked: false, textContent: '', checkValidity() {return true;}});
    return fields.get(id);
};
const context = vm.createContext({
    document: {getElementById: field, addEventListener() {}},
    window: {dashboardPricingSettings: {urban_premium_tariff_rate: .6, urban_premium_threshold_kw: 30}},
    console
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/dashboard.js'), 'utf8'), context);
field('urbanPremium').checked = true;
context.refreshUrbanPremiumLabel();
assert(field('urbanPremiumLabel').textContent.includes('30'));
assert(field('urbanPremiumLabel').textContent.includes('60'));
let quote = context.buildQuoteTemplateContext();
assert.equal(quote.tariff_threshold_kw, '30');
assert.equal(quote.tariff_first_agorot, '60');
assert.equal(quote.tariff_rate, '0.6');
field('urbanPremium').checked = false;
quote = context.buildQuoteTemplateContext();
assert.equal(quote.tariff_threshold_kw, '22.5');
assert.equal(quote.tariff_first_agorot, '48');

const admin = fs.readFileSync(path.join(__dirname, '../templates/admin.html'), 'utf8');
const start = admin.indexOf('        function updateUrbanPremiumPreview()');
const end = admin.indexOf("        ['urbanPremiumPreviewSize'", start);
vm.runInContext(admin.slice(start, end), context);
Object.entries({urbanPremiumPreviewSize: '60', productionPerKwp: '1600', urbanPremiumTariffRate: '0.6', urbanPremiumThresholdKw: '30', leasingPaymentRatio: '1'}).forEach(([id, value]) => {field(id).value = value;});
context.updateUrbanPremiumPreview();
assert(field('urbanPremiumPreview').textContent.includes('47,040'));
field('urbanPremiumTariffRate').value = '0.52';
field('urbanPremiumThresholdKw').value = '22.5';
context.updateUrbanPremiumPreview();
assert(field('urbanPremiumPreview').textContent.includes('41,520'));
field('leasingPaymentRatio').value = '0';
context.updateUrbanPremiumPreview();
assert(field('urbanPremiumPreview').textContent.includes('₪0'));
field('urbanPremiumTariffRate').value = '';
context.updateUrbanPremiumPreview();
assert(!field('urbanPremiumPreview').textContent.includes('₪'));

// Syntax-check all inline template scripts as well as the shared dashboard bundle.
for (const filename of ['admin.html', 'dashboard.html']) {
    const source = fs.readFileSync(path.join(__dirname, '../templates', filename), 'utf8');
    for (const match of source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
        new vm.Script(match[1]);
    }
}
console.log('PASS editable premium preview, configured quote labels/text, standard mode, zero share, and blank input');
